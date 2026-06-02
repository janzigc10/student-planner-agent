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
- `create_study_plan` 只负责生成候选计划；如果用户确认要写入日程，再把计划里的每个条目逐个 `create_task` 落库。
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
