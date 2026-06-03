import json
from datetime import datetime, timedelta
from typing import Any

from app.agent.llm_client import AsyncOpenAI, chat_completion, create_llm_client

WORK_PLAN_PROMPT = """你是一个学生作业/报告任务拆解器。根据以下信息生成候选任务：

作业或项目：
{work_items}

可用时间段：
{slots}

拆解策略：{strategy}

工作上下文：
{work_context}

要求：
1. 每个任务必须在一个空闲时段内，不能跨时段
2. 所有任务必须安排在截止日期之前，不能安排到截止日期之后
3. 每个任务的时长在 30-120 分钟之间
4. 如果 work_context 里有 daily_work_limit_minutes，同一天任务总时长不能超过该上限
5. 任务标题格式：\"作业/报告名 - 具体阶段\"
6. description 要具体写清楚该阶段要交付什么产物
7. 阶段要覆盖：明确要求/收集材料、提纲或方案、初稿/实现、修改完善、提交检查
8. 不要生成长期目标、学习习惯、泛泛建议；只生成可以写入日程的具体任务

输出格式（严格 JSON）：
[
  {{
    \"title\": \"机器学习报告 - 整理要求和资料\",
    \"work_item_name\": \"机器学习报告\",
    \"date\": \"YYYY-MM-DD\",
    \"start_time\": \"HH:MM\",
    \"end_time\": \"HH:MM\",
    \"description\": \"确认报告页数、PDF格式、实验结果和参考文献要求，并整理可用材料\"
  }}
]

只输出 JSON 数组，不要输出其他内容。"""


def _minutes_between(start_time: str, end_time: str) -> int | None:
    try:
        start = datetime.strptime(start_time, "%H:%M")
        end = datetime.strptime(end_time, "%H:%M")
    except ValueError:
        return None
    minutes = int((end - start).total_seconds() // 60)
    return minutes if minutes > 0 else None


def _add_minutes(start_time: str, minutes: int) -> str:
    start = datetime.strptime(start_time, "%H:%M")
    return (start + timedelta(minutes=minutes)).strftime("%H:%M")


def _limit_tasks_by_daily_cap(
    tasks: list[dict[str, Any]],
    daily_limit_minutes: int | None,
) -> list[dict[str, Any]]:
    if daily_limit_minutes is None or daily_limit_minutes <= 0:
        return tasks

    limited: list[dict[str, Any]] = []
    used_by_date: dict[str, int] = {}
    for task in sorted(tasks, key=lambda item: (str(item.get("date") or item.get("scheduled_date") or ""), str(item.get("start_time") or ""))):
        task_date = str(task.get("date") or task.get("scheduled_date") or "")
        start_time = str(task.get("start_time") or "")
        end_time = str(task.get("end_time") or "")
        duration = _minutes_between(start_time, end_time)
        if not task_date or duration is None:
            continue

        used = used_by_date.get(task_date, 0)
        remaining = daily_limit_minutes - used
        if remaining < 30:
            continue
        next_task = dict(task)
        capped_duration = min(duration, remaining, 120)
        if capped_duration < duration:
            next_task["end_time"] = _add_minutes(start_time, capped_duration)
        used_by_date[task_date] = used + capped_duration
        limited.append(next_task)

    return limited


def _fallback_work_plan(
    work_items: list[dict[str, Any]],
    available_slots: dict[str, Any],
    work_context: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not work_items:
        return []

    item = work_items[0]
    item_name = str(item.get("title") or item.get("name") or "作业任务").strip() or "作业任务"
    stages = [
        ("整理要求和资料", "确认交付要求、评分点、格式和已有材料，列出需要补齐的信息。"),
        ("完成提纲或方案", "搭建整体结构，明确每一部分要写什么或实现什么。"),
        ("完成初稿", "集中完成主体内容，保留待补充和待核对项。"),
        ("修改完善", "根据要求补充细节、检查逻辑、修正格式和引用。"),
        ("提交前检查", "核对文件格式、命名、引用、实验结果或附件，准备提交。"),
    ]

    tasks: list[dict[str, Any]] = []
    slot_days = available_slots.get("slots") if isinstance(available_slots, dict) else []
    if not isinstance(slot_days, list):
        return []

    daily_limit = None
    if isinstance(work_context, dict):
        raw_limit = work_context.get("daily_work_limit_minutes")
        if isinstance(raw_limit, int):
            daily_limit = raw_limit
    used_by_date: dict[str, int] = {}

    for day in slot_days:
        if not isinstance(day, dict):
            continue
        task_date = str(day.get("date") or "")
        periods = day.get("free_periods")
        if not task_date or not isinstance(periods, list):
            continue
        for period in periods:
            if not isinstance(period, dict) or len(tasks) >= len(stages):
                break
            duration = int(period.get("duration_minutes") or 0)
            if duration < 30:
                continue
            remaining = None if daily_limit is None else daily_limit - used_by_date.get(task_date, 0)
            if remaining is not None and remaining < 30:
                continue
            stage, description = stages[len(tasks)]
            start_time = str(period.get("start") or "")
            task_minutes = min(duration, 120, remaining) if remaining is not None else min(duration, 120)
            used_by_date[task_date] = used_by_date.get(task_date, 0) + task_minutes
            tasks.append(
                {
                    "title": f"{item_name} - {stage}",
                    "work_item_name": item_name,
                    "date": task_date,
                    "start_time": start_time,
                    "end_time": _add_minutes(start_time, task_minutes),
                    "description": description,
                }
            )

    if len(tasks) < 3:
        return []

    return _limit_tasks_by_daily_cap(tasks, daily_limit)


async def generate_work_plan(
    work_items: list[dict[str, Any]],
    available_slots: dict[str, Any],
    strategy: str = "staged",
    work_context: dict[str, Any] | None = None,
    llm_client: AsyncOpenAI | None = None,
) -> list[dict[str, Any]]:
    """Use an LLM to generate a deadline-oriented work plan with a deterministic fallback."""
    if llm_client is None:
        llm_client = create_llm_client()

    prompt = WORK_PLAN_PROMPT.format(
        work_items=json.dumps(work_items, ensure_ascii=False, indent=2),
        slots=json.dumps(available_slots, ensure_ascii=False, indent=2),
        strategy=strategy,
        work_context=json.dumps(work_context or {}, ensure_ascii=False, indent=2),
    )

    response = await chat_completion(
        llm_client,
        [{"role": "user", "content": prompt}],
    )

    content = response.get("content", "").strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1])

    tasks: list[dict[str, Any]] = []
    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            tasks = [task for task in parsed if isinstance(task, dict)]
    except json.JSONDecodeError:
        tasks = []

    if not tasks:
        tasks = _fallback_work_plan(work_items, available_slots, work_context)

    daily_limit = None
    if isinstance(work_context, dict):
        raw_limit = work_context.get("daily_work_limit_minutes")
        if isinstance(raw_limit, int):
            daily_limit = raw_limit
    return _limit_tasks_by_daily_cap(tasks, daily_limit)
