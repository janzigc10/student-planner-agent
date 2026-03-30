"""Session end processing: generate summary and extract memories."""

import json
import logging

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_client import chat_completion
from app.models.conversation_message import ConversationMessage
from app.models.memory import Memory
from app.models.session_summary import SessionSummary

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = """请分析下面这段会话，并严格输出 JSON：
{
  "summary": "一句话总结本次会话",
  "actions": ["本次会话中执行过的动作"],
  "memories": [
    {"category": "preference|habit|decision|knowledge", "content": "值得长期记住的信息"}
  ]
}

规则：
- summary 保持简洁
- memories 只提取用户明确表达的偏好、习惯、决策或知识认知
- 没有可保存的记忆时返回空数组
- 只输出 JSON，不要输出其他说明"""


async def end_session(
    db: AsyncSession,
    user_id: str,
    session_id: str,
    llm_client: AsyncOpenAI,
) -> None:
    """Generate a session summary and extract memories at session end."""
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.timestamp)
    )
    messages = list(result.scalars().all())

    if not messages:
        return

    conversation_text = "\n".join(
        f"{message.role}: {message.content}" for message in messages if message.content
    )

    try:
        response = await chat_completion(
            llm_client,
            [
                {"role": "system", "content": _EXTRACT_PROMPT},
                {"role": "user", "content": conversation_text},
            ],
        )
        content = (response.get("content") or "").strip()
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(lines[1:-1]).strip()
        data = json.loads(content)
    except Exception:
        logger.warning("Failed to finalize session %s", session_id, exc_info=True)
        return

    summary_text = data.get("summary", "")
    actions = data.get("actions", [])
    if summary_text:
        db.add(
            SessionSummary(
                user_id=user_id,
                session_id=session_id,
                summary=summary_text,
                actions_taken=actions,
            )
        )

    for memory_data in data.get("memories", []):
        category = memory_data.get("category", "")
        content = memory_data.get("content", "")
        if category and content:
            db.add(
                Memory(
                    user_id=user_id,
                    category=category,
                    content=content,
                    source_session_id=session_id,
                )
            )

    await db.commit()