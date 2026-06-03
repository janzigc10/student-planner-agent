import json
from datetime import datetime, timedelta
from typing import Any

from app.agent.llm_client import AsyncOpenAI, chat_completion, create_llm_client

PLAN_PROMPT = """你是一个复习计划生成器。根据以下信息生成复习计划：

考试列表：
{exams}

可用时间段：
{slots}

复习策略：{strategy}
- balanced：每门课均匀分配时间
- intensive：考前几天集中复习
- spaced：间隔重复，越早开始越好

学习上下文：
{study_context}

要求：
1. 每个任务必须在一个空闲时段内，不能跨时段
2. 难度高的课程分配更多时间
3. 同一门课的复习任务不要连续安排（除非时间不够）
4. 每个任务的时长在 1-2 小时之间
5. 任务标题格式：\"课程名 - 具体内容\"
6. description 要具体，写清楚复习哪些章节/知识点
7. 如果学习上下文里有 exam_scope，任务描述必须覆盖这些章节/单元/知识点
8. 如果学习上下文里有 weak_areas，至少安排对应专项任务，并在标题或 description 里体现
9. 如果学习上下文里有 daily_study_limit_minutes，同一天任务总时长不能超过该上限
10. 计划节奏应包含基础覆盖、薄弱突破、综合练习、错题/考前回顾，不要只是平均铺时间
11. 如果 using_defaults 为 true，要在 description 中写清楚这是按默认假设安排，不要假装知道具体范围

示例输入：
考试：高等数学(4月5日, hard), 线性代数(4月5日, medium)
空闲：3月30日 10:00-12:00, 14:00-17:00; 3月31日 10:00-12:00, 14:00-16:00
策略：balanced

示例输出：
[
  {{
    \"title\": \"高数 - 极限与连续\",
    \"exam_name\": \"高等数学\",
    \"date\": \"2026-03-30\",
    \"start_time\": \"10:00\",
    \"end_time\": \"12:00\",
    \"description\": \"复习第1-3章：极限定义、夹逼定理、连续性判断、间断点分类\"
  }},
  {{
    \"title\": \"线代 - 行列式与矩阵\",
    \"exam_name\": \"线性代数\",
    \"date\": \"2026-03-30\",
    \"start_time\": \"14:00\",
    \"end_time\": \"16:00\",
    \"description\": \"复习第1-2章：行列式计算、矩阵运算、逆矩阵求法\"
  }},
  {{
    \"title\": \"高数 - 微分与积分\",
    \"exam_name\": \"高等数学\",
    \"date\": \"2026-03-30\",
    \"start_time\": \"16:00\",
    \"end_time\": \"17:00\",
    \"description\": \"复习第4-5章：导数计算、微分中值定理、不定积分基本方法\"
  }},
  {{
    \"title\": \"线代 - 向量与线性方程组\",
    \"exam_name\": \"线性代数\",
    \"date\": \"2026-03-31\",
    \"start_time\": \"10:00\",
    \"end_time\": \"12:00\",
    \"description\": \"复习第3-4章：向量空间、线性相关性、齐次/非齐次方程组求解\"
  }},
  {{
    \"title\": \"高数 - 综合练习\",
    \"exam_name\": \"高等数学\",
    \"date\": \"2026-03-31\",
    \"start_time\": \"14:00\",
    \"end_time\": \"16:00\",
    \"description\": \"做2套历年真题，重点关注计算题和证明题\"
  }}
]

注意示例中的特点：
- 高数(hard)分配了3个时段，线代(medium)分配了2个时段 — 难度高的课更多时间
- 高数和线代交替安排，没有连续复习同一门课
- 最后一个任务是综合练习，不只是看书
- description 具体到章节和知识点

输出格式（严格 JSON）：
[
  {{
    \"title\": \"课程名 - 具体内容\",
    \"exam_name\": \"课程全名\",
    \"date\": \"YYYY-MM-DD\",
    \"start_time\": \"HH:MM\",
    \"end_time\": \"HH:MM\",
    \"description\": \"具体复习内容，包含章节和知识点\"
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


def _daily_limit_from_context(study_context: dict[str, Any] | None) -> int | None:
    if not isinstance(study_context, dict):
        return None
    value = study_context.get("daily_study_limit_minutes")
    return value if isinstance(value, int) and value > 0 else None


def _fallback_study_plan(
    exams: list[dict[str, Any]],
    available_slots: dict[str, Any],
    study_context: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not exams:
        return []
    slot_days = available_slots.get("slots") if isinstance(available_slots, dict) else []
    if not isinstance(slot_days, list):
        return []

    stages = ["基础覆盖", "薄弱突破", "综合练习", "错题回顾"]
    daily_limit = _daily_limit_from_context(study_context)
    used_by_date: dict[str, int] = {}
    counts_by_exam: dict[str, int] = {}
    tasks: list[dict[str, Any]] = []
    raw_scope = ""
    weak_text = ""
    if isinstance(study_context, dict):
        raw_scope = str(study_context.get("exam_scope") or study_context.get("raw_notes") or "").strip()
        weak_areas = study_context.get("weak_areas")
        if isinstance(weak_areas, list) and weak_areas:
            weak_text = "、".join(str(item) for item in weak_areas if str(item).strip())

    for day in slot_days:
        if not isinstance(day, dict):
            continue
        task_date = str(day.get("date") or "")
        periods = day.get("free_periods")
        if not task_date or not isinstance(periods, list):
            continue
        eligible_exams = [
            exam
            for exam in exams
            if isinstance(exam, dict)
            and str(exam.get("course_name") or "").strip()
            and str(exam.get("exam_date") or "") > task_date
        ]
        if not eligible_exams:
            continue
        for period in periods:
            if not isinstance(period, dict):
                continue
            duration = int(period.get("duration_minutes") or 0)
            if duration < 30:
                continue
            remaining = None if daily_limit is None else daily_limit - used_by_date.get(task_date, 0)
            if remaining is not None and remaining < 30:
                continue
            exam = min(
                eligible_exams,
                key=lambda item: (
                    counts_by_exam.get(str(item.get("course_name") or ""), 0),
                    str(item.get("exam_date") or ""),
                ),
            )
            course_name = str(exam.get("course_name") or "").strip()
            stage = stages[counts_by_exam.get(course_name, 0) % len(stages)]
            start_time = str(period.get("start") or "")
            task_minutes = min(duration, 120, remaining) if remaining is not None else min(duration, 120)
            topic = raw_scope or "按默认考试范围"
            if weak_text and stage == "薄弱突破":
                topic = f"{topic}；重点突破{weak_text}"
            description = f"{stage}：围绕{topic}安排{course_name}复习，产出错题或知识点清单。"
            tasks.append(
                {
                    "title": f"{course_name} - {stage}",
                    "exam_name": course_name,
                    "date": task_date,
                    "start_time": start_time,
                    "end_time": _add_minutes(start_time, task_minutes),
                    "description": description,
                }
            )
            used_by_date[task_date] = used_by_date.get(task_date, 0) + task_minutes
            counts_by_exam[course_name] = counts_by_exam.get(course_name, 0) + 1

    return tasks


def _task_mentions_course(task: dict[str, Any], course_name: str) -> bool:
    haystack = "\n".join(
        str(task.get(key) or "")
        for key in ("title", "exam_name", "course_name", "description")
    )
    return course_name in haystack


def _ensure_exam_coverage(
    tasks: list[dict[str, Any]],
    exams: list[dict[str, Any]],
    available_slots: dict[str, Any],
    study_context: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    course_names = [
        str(exam.get("course_name") or "").strip()
        for exam in exams
        if isinstance(exam, dict) and str(exam.get("course_name") or "").strip()
    ]
    if len(course_names) <= 1:
        return tasks

    missing_courses = [
        course_name
        for course_name in course_names
        if not any(_task_mentions_course(task, course_name) for task in tasks)
    ]
    if not missing_courses:
        return tasks

    fallback_tasks = _fallback_study_plan(exams, available_slots, study_context)
    additions = [
        task
        for task in fallback_tasks
        if any(_task_mentions_course(task, course_name) for course_name in missing_courses)
    ]
    existing_keys = {
        (
            str(task.get("title") or ""),
            str(task.get("date") or task.get("scheduled_date") or ""),
            str(task.get("start_time") or ""),
        )
        for task in tasks
    }
    for task in additions:
        key = (
            str(task.get("title") or ""),
            str(task.get("date") or task.get("scheduled_date") or ""),
            str(task.get("start_time") or ""),
        )
        if key in existing_keys:
            continue
        tasks.append(task)
        existing_keys.add(key)
    return tasks


async def generate_study_plan(
    exams: list[dict[str, Any]],
    available_slots: dict[str, Any],
    strategy: str = "balanced",
    study_context: dict[str, Any] | None = None,
    llm_client: AsyncOpenAI | None = None,
) -> list[dict[str, Any]]:
    """Use LLM to generate a study plan."""
    if llm_client is None:
        llm_client = create_llm_client()

    prompt = PLAN_PROMPT.format(
        exams=json.dumps(exams, ensure_ascii=False, indent=2),
        slots=json.dumps(available_slots, ensure_ascii=False, indent=2),
        strategy=strategy,
        study_context=json.dumps(study_context or {}, ensure_ascii=False, indent=2),
    )

    response = await chat_completion(
        llm_client,
        [{"role": "user", "content": prompt}],
    )

    content = response.get("content", "").strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1])

    try:
        tasks = json.loads(content)
        if not isinstance(tasks, list):
            return _fallback_study_plan(exams, available_slots, study_context)
        normalized_tasks = [task for task in tasks if isinstance(task, dict)]
        return _ensure_exam_coverage(normalized_tasks, exams, available_slots, study_context)
    except json.JSONDecodeError:
        return _fallback_study_plan(exams, available_slots, study_context)
