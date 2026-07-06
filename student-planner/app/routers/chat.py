import uuid
from collections.abc import Iterator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.agent.langgraph_loop import run_langgraph_agent_loop
from app.agent.llm_client import create_llm_client
from app.agent.loop import run_review_override_plan_write
from app.agent.session_lifecycle import end_session
from app.auth.jwt import verify_token
from app.config import settings
from app.database import get_db
from app.models.user import User

router = APIRouter(tags=["chat"])

LLM_PROVIDER_UNAVAILABLE_CODE = "llm_provider_unavailable"
LLM_PROVIDER_UNAVAILABLE_MESSAGE = (
    "模型服务暂时连接不上，刚才的操作还没有执行。"
    "请稍后重试，或检查当前网络/模型服务配置。"
)
GENERIC_CHAT_ERROR_MESSAGE = "聊天暂时不可用，请稍后重试"


def _select_agent_loop():
    return run_langgraph_agent_loop


def _iter_exception_chain(exc: BaseException) -> Iterator[BaseException]:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _is_llm_provider_unavailable(exc: BaseException) -> bool:
    provider_error_names = {
        "APIConnectionError",
        "APITimeoutError",
        "APIStatusError",
        "APIError",
        "RateLimitError",
        "InternalServerError",
        "AuthenticationError",
        "PermissionDeniedError",
        "BadRequestError",
    }
    network_markers = (
        "apiconnectionerror",
        "apitimeouterror",
        "authenticationerror",
        "permissiondeniederror",
        "badrequesterror",
        "data_inspection_failed",
        "failed to establish",
        "network is unreachable",
        "connection refused",
        "connection reset",
        "temporary failure",
        "timed out",
        "timeout",
        "winerror 5",
    )

    for item in _iter_exception_chain(exc):
        class_name = item.__class__.__name__
        module_name = item.__class__.__module__
        if module_name.startswith("openai") and class_name in provider_error_names:
            return True
        if isinstance(item, TimeoutError | ConnectionError):
            return True

        text = f"{class_name}: {item}".lower()
        if any(marker in text for marker in network_markers):
            return True

    return False


def _chat_error_event(exc: BaseException) -> dict[str, object]:
    if _is_llm_provider_unavailable(exc):
        return {
            "type": "error",
            "code": LLM_PROVIDER_UNAVAILABLE_CODE,
            "recoverable": True,
            "message": LLM_PROVIDER_UNAVAILABLE_MESSAGE,
        }
    return {"type": "error", "message": GENERIC_CHAT_ERROR_MESSAGE}


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    user_id: str | None = None
    session_id: str | None = None
    llm_client = None

    try:
        auth_message = await websocket.receive_json()
        token = auth_message.get("token")
        if not token:
            await websocket.send_json({"type": "error", "message": "Missing token"})
            await websocket.close()
            return

        user_id = verify_token(token)
        if not user_id:
            await websocket.send_json({"type": "error", "message": "Invalid token"})
            await websocket.close()
            return
    except WebSocketDisconnect:
        return
    except RuntimeError:
        return
    except Exception:
        try:
            await websocket.close()
        except RuntimeError:
            pass
        return

    session_id = str(uuid.uuid4())
    llm_client = create_llm_client()
    try:
        await websocket.send_json({"type": "connected", "session_id": session_id})
    except (RuntimeError, WebSocketDisconnect):
        return

    try:
        while True:
            data = await websocket.receive_json()
            user_message = str(data.get("message") or "").strip()
            if not user_message:
                orphan_answer = str(data.get("answer") or "").strip()
                if orphan_answer:
                    if "review_override=" in orphan_answer and session_id is not None:
                        async for db in get_db():
                            result = await db.execute(select(User).where(User.id == user_id))
                            user = result.scalar_one_or_none()
                            if user is None:
                                await websocket.send_json({"type": "error", "message": "User not found"})
                                break

                            async for event in run_review_override_plan_write(
                                orphan_answer,
                                user,
                                session_id,
                                db,
                            ):
                                await websocket.send_json(event)
                            break
                        continue

                    try:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "当前没有待确认的问题，请先发送消息或重新触发操作。",
                            }
                        )
                    except (RuntimeError, WebSocketDisconnect):
                        return
                continue

            async for db in get_db():
                result = await db.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
                if user is None:
                    await websocket.send_json({"type": "error", "message": "User not found"})
                    break

                generator = _select_agent_loop()(user_message, user, session_id, db, llm_client)
                try:
                    event = await generator.__anext__()
                    while True:
                        await websocket.send_json(event)
                        if event["type"] == "ask_user":
                            while True:
                                user_response = await websocket.receive_json()
                                user_answer = (
                                    user_response.get("answer")
                                    or user_response.get("message")
                                    or ""
                                ).strip()
                                if user_answer:
                                    break
                                await websocket.send_json(
                                    {"type": "error", "message": "请输入回复内容后再提交"}
                                )
                            event = await generator.asend(user_answer)
                        elif event["type"] == "done":
                            break
                        else:
                            event = await generator.__anext__()
                except StopAsyncIteration:
                    pass
                except WebSocketDisconnect:
                    return
                except Exception as exc:
                    try:
                        await websocket.send_json(_chat_error_event(exc))
                    except (RuntimeError, WebSocketDisconnect):
                        return
    except WebSocketDisconnect:
        return
    finally:
        if user_id and session_id and llm_client is not None:
            async for db in get_db():
                await end_session(db, user_id, session_id, llm_client)
