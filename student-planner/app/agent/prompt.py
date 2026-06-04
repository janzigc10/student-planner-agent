from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import build_dynamic_context
from app.models.user import User

AGENT_MD_PATH = Path(__file__).parent.parent.parent / "Agent.md"
TASK_TOOL_RULES = """## 普通任务与提醒补充规则
- 用户要创建一个新的普通任务时，先用 `ask_user` 确认，再调用 `create_task`。
- 绝不要用 `update_task` 创建新任务，也不要传入占位 task_id，例如 `new`。
- 用户在创建任务时同时要求提醒，优先把 `reminder_advance_minutes` 直接传给 `create_task`，不要拆成 `create_task` 后再 `set_reminder`。
- 用户修改任务时间时同时要求修改提醒，先确认，再把新时间和 `reminder_advance_minutes` 一起传给 `update_task`。
- 用户明确说“不提醒 / 不用提醒 / 取消提醒 / 删除提醒”时，不要说系统不能删除提醒；先确认，再调用 `update_task`，并传入 `reminder_advance_minutes=null` 删除已有普通任务提醒。
- 用户只改任务时间、没有明确改提醒时，调用 `update_task` 更新任务时间；已有 task reminder 会跟随新时间重算。
- 所有任务/提醒相关的确认、补充信息、缺参数追问都必须调用 `ask_user`，禁止用普通 assistant 文本问用户“是否确认”“哪天/几点”。
- 用户要纠正、改名、合并或删除当前课表里的课程时，先 `list_courses`，不要要求重新上传课表；确认后再 `update_course` 或 `delete_course`，同名多条且缺少周几/时间/地点时先澄清。
- `create_study_plan` 只负责生成候选计划；如果用户确认要写入日程，再把计划里的每个条目逐个 `create_task` 落库。
- 生成复习计划前，如果用户只是简单要求安排复习且考试课程/日期已明确，不要强行追问复习范围、薄弱点、目标成绩或每日上限；直接用默认均衡策略，并在 `study_context` 写入 `{"using_defaults": true, "raw_notes": "按默认"}`。只有用户明确要求详细、精准、冲刺、定制或针对性计划且缺少这些上下文时，才用 `ask_user` 补一次。
- 调用 `create_study_plan` 时，把已知学习上下文写入 `study_context`，包括 `exam_scope`、`weak_areas`、`target_score`、`daily_study_limit_minutes` 和 `raw_notes`。
- `create_work_plan` 只负责生成作业、报告、大作业、实验报告、论文、项目或展示的候选任务；确认写入日程时仍要逐条调用 `create_task`。
- 生成作业/报告计划前，如果只有截止日期和标题，缺少交付要求、格式、已完成进度或每日最大可工作时长，必须先用 `ask_user` 补一次工作上下文；用户回复“按默认”时才可按默认假设继续。
- 调用 `create_work_plan` 时，把已知工作上下文写入 `work_context`，包括 `requirements`、`current_progress`、`daily_work_limit_minutes` 和 `raw_notes`。
- 确认写入候选复习计划或作业计划时，如果某条 `create_task` 因原时间冲突失败，可以在同一计划日期范围内重新查询空闲段并自动重排；找不到可用空档时再提示该条未写入。
- 用户要求调整近期计划且明确说“太满/每天最多 N 小时或分钟”时，先列出现有任务并确认，再用 `update_task` 调整；找不到匹配任务时不要乱改。
- 最终回复必须依据工具返回结果，不要在工具未成功返回时声称“全部完成”。
"""


def load_agent_md() -> str:
    """Load Agent.md static rules."""
    return AGENT_MD_PATH.read_text(encoding="utf-8")


async def build_system_prompt(user: User, db: AsyncSession) -> str:
    """Assemble full system prompt = Agent.md + task rules + dynamic context."""
    agent_md = load_agent_md()
    dynamic_context = await build_dynamic_context(user, db)
    return f"{agent_md}\n\n---\n\n{TASK_TOOL_RULES}\n\n---\n\n## 当前上下文\n{dynamic_context}"
