from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.models.user import User
from tests.conftest import TestSession


def test_chat_error_event_classifies_openai_authentication_error():
    from app.routers.chat import _chat_error_event

    class AuthenticationError(Exception):
        pass

    AuthenticationError.__module__ = "openai"

    event = _chat_error_event(AuthenticationError("invalid api key"))

    assert event == {
        "type": "error",
        "code": "llm_provider_unavailable",
        "recoverable": True,
        "message": "模型服务暂时连接不上，刚才的操作还没有执行。请稍后重试，或检查当前网络/模型服务配置。",
    }


def test_chat_error_event_classifies_provider_bad_request():
    from app.routers.chat import _chat_error_event

    class BadRequestError(Exception):
        pass

    BadRequestError.__module__ = "openai"

    event = _chat_error_event(BadRequestError("data_inspection_failed"))

    assert event["type"] == "error"
    assert event["code"] == "llm_provider_unavailable"
    assert event["recoverable"] is True


@pytest.mark.asyncio
async def test_ws_auth_required(client):
    """WebSocket route should be registered."""
    from app.database import get_db
    from app.main import create_app

    app = create_app()

    async def override_get_db():
        async with TestSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    routes = [route.path for route in app.routes]
    assert "/ws/chat" in routes


@pytest.mark.asyncio
async def test_ws_returns_error_event_when_agent_loop_raises(setup_db):
    from app.main import create_app

    app = create_app()

    async def override_get_db():
        async with TestSession() as session:
            yield session

    async with TestSession() as session:
        user = User(username="ws-user", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    async def failing_agent_loop(*args, **kwargs):
        raise RuntimeError("boom")
        yield {}

    token = create_access_token(user_id)

    with (
        patch("app.routers.chat.create_llm_client", return_value=AsyncMock()),
        patch("app.routers.chat.get_db", side_effect=override_get_db),
        patch("app.routers.chat.run_agent_loop", side_effect=failing_agent_loop),
        patch("app.routers.chat.end_session", new_callable=AsyncMock),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        with client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json({"token": token})
            assert websocket.receive_json()["type"] == "connected"

            websocket.send_json({"message": "help me plan today"})
            event = websocket.receive_json()

        assert event["type"] == "error"
        assert event["message"] == "聊天暂时不可用，请稍后重试"


@pytest.mark.asyncio
async def test_ws_returns_recoverable_provider_error_when_agent_loop_network_fails(setup_db):
    from app.main import create_app

    app = create_app()

    async def override_get_db():
        async with TestSession() as session:
            yield session

    async with TestSession() as session:
        user = User(username="ws-provider-user", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    async def failing_agent_loop(*args, **kwargs):
        raise PermissionError("[WinError 5] 拒绝访问。")
        yield {}

    token = create_access_token(user_id)

    with (
        patch("app.routers.chat.create_llm_client", return_value=AsyncMock()),
        patch("app.routers.chat.get_db", side_effect=override_get_db),
        patch("app.routers.chat.run_agent_loop", side_effect=failing_agent_loop),
        patch("app.routers.chat.end_session", new_callable=AsyncMock),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        with client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json({"token": token})
            assert websocket.receive_json()["type"] == "connected"

            websocket.send_json({"message": "help me plan today"})
            event = websocket.receive_json()

        assert event == {
            "type": "error",
            "code": "llm_provider_unavailable",
            "recoverable": True,
            "message": "模型服务暂时连接不上，刚才的操作还没有执行。请稍后重试，或检查当前网络/模型服务配置。",
        }


@pytest.mark.asyncio
async def test_ws_disconnect_while_waiting_for_ask_user_answer_is_graceful(setup_db):
    from app.main import create_app

    app = create_app()

    async def override_get_db():
        async with TestSession() as session:
            yield session

    async with TestSession() as session:
        user = User(username="ws-user-2", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    async def ask_then_wait(*args, **kwargs):
        yield {
            "type": "ask_user",
            "question": "please provide period times",
            "ask_type": "review",
            "options": [],
            "data": None,
        }
        yield {"type": "done"}

    token = create_access_token(user_id)

    with (
        patch("app.routers.chat.create_llm_client", return_value=AsyncMock()),
        patch("app.routers.chat.get_db", side_effect=override_get_db),
        patch("app.routers.chat.run_agent_loop", side_effect=ask_then_wait),
        patch("app.routers.chat.end_session", new_callable=AsyncMock) as mock_end_session,
    ):
        client = TestClient(app)
        with client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json({"token": token})
            assert websocket.receive_json()["type"] == "connected"

            websocket.send_json({"message": "please continue"})
            event = websocket.receive_json()
            assert event["type"] == "ask_user"

        mock_end_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_ws_returns_error_for_orphan_answer_payload(setup_db):
    from app.main import create_app

    app = create_app()

    async def override_get_db():
        async with TestSession() as session:
            yield session

    async with TestSession() as session:
        user = User(username="ws-user-3", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    async def done_only_agent_loop(*args, **kwargs):
        yield {"type": "done"}

    token = create_access_token(user_id)

    with (
        patch("app.routers.chat.create_llm_client", return_value=AsyncMock()),
        patch("app.routers.chat.get_db", side_effect=override_get_db),
        patch("app.routers.chat.run_agent_loop", side_effect=done_only_agent_loop),
        patch("app.routers.chat.end_session", new_callable=AsyncMock),
    ):
        client = TestClient(app)
        with client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json({"token": token})
            assert websocket.receive_json()["type"] == "connected"

            websocket.send_json({"answer": "confirm"})
            websocket.send_json({"message": "continue"})

            first_event = websocket.receive_json()

        assert first_event == {
            "type": "error",
            "message": "当前没有待确认的问题，请先发送消息或重新触发操作。",
        }
