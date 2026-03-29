import json
from typing import Any, AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.guardrails import (
    GuardrailViolation,
    check_consecutive_ask_user,
    check_max_loop_iterations,
    check_max_retries,
    check_unknown_tool,
)
from app.agent.llm_client import AsyncOpenAI, chat_completion
from app.agent.prompt import build_system_prompt
from app.agent.tool_executor import execute_tool
from app.agent.tools import TOOL_DEFINITIONS
from app.models.agent_log import AgentLog
from app.models.conversation_message import ConversationMessage
from app.models.user import User

KNOWN_TOOLS = {tool["function"]["name"] for tool in TOOL_DEFINITIONS}
MAX_ITERATIONS = 20


async def run_agent_loop(
    user_message: str,
    user: User,
    session_id: str,
    db: AsyncSession,
    llm_client: AsyncOpenAI,
) -> AsyncGenerator[dict[str, Any], str | None]:
    """Run the agent loop and yield frontend events."""
    system_prompt = await build_system_prompt(user, db)

    history_result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.timestamp)
    )
    history_messages = history_result.scalars().all()

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for message in history_messages:
        messages.append({"role": message.role, "content": message.content})

    messages.append({"role": "user", "content": user_message})
    await _save_message(db, session_id, "user", user_message)

    tool_history: list[str] = []
    error_count: dict[str, int] = {}
    step = 0

    for iteration in range(MAX_ITERATIONS):
        check_max_loop_iterations(iteration, MAX_ITERATIONS)
        response = await chat_completion(llm_client, messages, tools=TOOL_DEFINITIONS)

        if "tool_calls" not in response:
            text = response.get("content", "")
            if text:
                yield {"type": "text", "content": text}
                await _save_message(db, session_id, "assistant", text)
            yield {"type": "done"}
            return

        messages.append(response)

        for tool_call in response["tool_calls"]:
            tool_name = tool_call["function"]["name"]
            tool_args_str = tool_call["function"]["arguments"]
            tool_call_id = tool_call["id"]

            try:
                tool_args = json.loads(tool_args_str)
            except json.JSONDecodeError:
                tool_args = {}

            try:
                check_unknown_tool(tool_name, KNOWN_TOOLS)
                if tool_name == "ask_user":
                    check_consecutive_ask_user(tool_history + [tool_name])
                else:
                    check_consecutive_ask_user(tool_history)
                check_max_retries(tool_name, error_count)
            except GuardrailViolation as exc:
                tool_result = {"error": exc.message, "suggestion": exc.suggestion}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )
                yield {"type": "error", "message": exc.message}
                continue

            yield {"type": "tool_call", "name": tool_name, "args": tool_args}

            if tool_name == "ask_user":
                result = await execute_tool(tool_name, tool_args, db, user.id)
                user_response = yield {"type": "ask_user", **result}
                if user_response is None:
                    user_response = "确认"
                tool_result_content = json.dumps({"user_response": user_response}, ensure_ascii=False)
            else:
                result = await execute_tool(tool_name, tool_args, db, user.id)
                tool_result_content = json.dumps(result, ensure_ascii=False)
                if "error" in result:
                    error_count[tool_name] = error_count.get(tool_name, 0) + 1
                yield {"type": "tool_result", "name": tool_name, "result": result}

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": tool_result_content,
                }
            )

            step += 1
            tool_history.append(tool_name)
            await _log_step(db, user.id, session_id, step, tool_name, tool_args, result)

    yield {"type": "error", "message": "Agent loop 达到最大迭代次数"}
    yield {"type": "done"}


async def _save_message(db: AsyncSession, session_id: str, role: str, content: str) -> None:
    message = ConversationMessage(session_id=session_id, role=role, content=content)
    db.add(message)
    await db.commit()


async def _log_step(
    db: AsyncSession,
    user_id: str,
    session_id: str,
    step: int,
    tool_name: str,
    tool_args: dict[str, Any],
    tool_result: dict[str, Any],
) -> None:
    log = AgentLog(
        user_id=user_id,
        session_id=session_id,
        step=step,
        tool_called=tool_name,
        tool_args=tool_args,
        tool_result=tool_result,
    )
    db.add(log)
    await db.commit()