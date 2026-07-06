import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.agent.loop import _build_course_routing_hint, run_agent_loop
from app.models.conversation_message import ConversationMessage
from app.models.course import Course
from app.models.user import User
from app.services.memory_service import create_memory
from app.services.schedule_upload_cache import store_schedule_upload
from tests.conftest import TestSession


FIRST_STREAM_DELTA_TIMEOUT_SECONDS = 0.3


def stream_response_chunks(*, response: dict, deltas: list[str] | None = None):
    async def _generator():
        for delta in deltas or []:
            yield {"type": "content_delta", "delta": delta}
        yield {"type": "response", "response": response}

    return _generator()


def gated_stream_response_chunks(
    *,
    response: dict,
    allow_response: asyncio.Event,
    deltas: list[str] | None = None,
):
    async def _generator():
        for delta in deltas or []:
            yield {"type": "content_delta", "delta": delta}
        await allow_response.wait()
        yield {"type": "response", "response": response}

    return _generator()


def test_build_course_routing_hint_for_existing_course_correction():
    hint = _build_course_routing_hint(
        "你直接帮我优化成一门课吧，我现在日历里看还是两门课",
        [],
    )

    assert hint is not None
    assert "list_courses" in hint
    assert "update_course" in hint
    assert "不要要求用户重新上传文件" in hint


def test_build_course_routing_hint_for_followup_course_names():
    history = [
        ConversationMessage(
            session_id="session-routing",
            role="assistant",
            content='你说的"两门课"是指哪两门？是想合并成一门，还是删掉其中一门？帮我确认一下具体是哪两门课。',
        )
    ]

    hint = _build_course_routing_hint(
        "就是机器人程序动化和机器人流程自动化还有大模型微调技术和大型微调技术",
        history,
    )

    assert hint is not None
    assert "list_courses" in hint
    assert "update_course" in hint


def test_build_course_routing_hint_skips_schedule_import_requests():
    hint = _build_course_routing_hint(
        "我上传了课表文件 file_id=abc123，请帮我导入",
        [],
    )

    assert hint is None


@pytest.mark.asyncio
async def test_simple_text_response(setup_db):
    """LLM returns text without tool calls and loop ends immediately."""
    mock_client = AsyncMock()

    with patch("app.agent.loop.chat_completion_stream") as mock_chat_completion_stream:
        mock_chat_completion_stream.return_value = stream_response_chunks(
            response={"role": "assistant", "content": "Hello there."},
            deltas=["Hello ", "there."],
        )

        async with TestSession() as db:
            user = User(id="u1", username="test", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            generator = run_agent_loop("hi", user, "session-1", db, mock_client)
            async for event in generator:
                events.append(event)

            assert any(event["type"] == "text_delta" for event in events)
            assert any(event["type"] == "text" for event in events)
            assert any(event["type"] == "done" for event in events)
            text_event = next(event for event in events if event["type"] == "text")
            assert text_event["content"] == "Hello there."


@pytest.mark.asyncio
async def test_current_public_event_request_does_not_call_llm_or_claim_web(setup_db):
    mock_client = AsyncMock()

    with patch(
        "app.agent.loop.chat_completion_stream",
        side_effect=AssertionError("Current public event questions should not reach the LLM"),
    ), patch(
        "app.agent.loop.chat_completion",
        side_effect=AssertionError("Current public event questions should not reach the LLM fallback"),
    ):
        async with TestSession() as db:
            user = User(id="u-current-events", username="current-events", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            generator = run_agent_loop("中国最新的大事件有什么", user, "session-current-events", db, mock_client)
            async for event in generator:
                events.append(event)

            assert [event["type"] for event in events] == ["text", "done"]
            text = events[0]["content"]
            assert "没有联网检索" in text
            assert "不能可靠回答" in text
            assert "公开权威" not in text


@pytest.mark.asyncio
async def test_agent_loop_compresses_persisted_history_before_current_turn(setup_db):
    mock_client = AsyncMock()
    session_id = "session-history-compression"
    llm_messages_by_call: list[list[dict]] = []
    call_count = 0

    compressed_history = [
        {"role": "system", "content": "compressed system prompt"},
        {"role": "user", "content": "[之前的对话摘要] 用户之前持续调整过任务和提醒。"},
        {"role": "assistant", "content": "最近一轮保留的助手回复。"},
    ]

    def mock_chat_completion_stream(client, messages, tools=None):
        nonlocal call_count
        call_count += 1
        llm_messages_by_call.append(messages)
        if call_count == 1:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "list_courses", "arguments": "{}"},
                        }
                    ],
                }
            )
        return stream_response_chunks(
            response={"role": "assistant", "content": "当前没有课程。"},
        )

    with (
        patch(
            "app.agent.loop.compress_conversation_history",
            new_callable=AsyncMock,
            return_value=compressed_history,
        ) as mock_compress,
        patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream),
    ):
        async with TestSession() as db:
            user = User(id="u-history-compression", username="history-compression", hashed_password="x")
            db.add(user)
            db.add_all(
                [
                    ConversationMessage(
                        session_id=session_id,
                        role="user" if index % 2 == 0 else "assistant",
                        content=f"旧消息 {index}",
                    )
                    for index in range(30)
                ]
            )
            await db.commit()

            events = []
            generator = run_agent_loop("看一下当前课表", user, session_id, db, mock_client)
            async for event in generator:
                events.append(event)

    assert mock_compress.await_count == 1
    compressor_input = mock_compress.await_args.args[0]
    assert any(message.get("content") == "旧消息 0" for message in compressor_input)
    assert not any(message.get("content") == "看一下当前课表" for message in compressor_input)

    first_llm_messages = llm_messages_by_call[0]
    assert any("[之前的对话摘要]" in str(message.get("content")) for message in first_llm_messages)
    assert any(message.get("role") == "user" and message.get("content") == "看一下当前课表" for message in first_llm_messages)
    assert not any(message.get("content") == "旧消息 0" for message in first_llm_messages)

    second_llm_messages = llm_messages_by_call[1]
    assert any(message.get("role") == "tool" for message in second_llm_messages)
    assert any(event["type"] == "tool_call" and event["name"] == "list_courses" for event in events)
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_tool_call_then_text(setup_db):
    """LLM calls a tool, gets result, then responds with text."""
    mock_client = AsyncMock()
    call_count = 0

    def mock_chat_completion_stream(client, messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "list_courses", "arguments": "{}"},
                        }
                    ],
                }
            )
        return stream_response_chunks(
            response={"role": "assistant", "content": "You currently have no courses."},
            deltas=["You currently ", "have no courses."],
        )

    with patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream):
        async with TestSession() as db:
            user = User(id="u2", username="test2", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            generator = run_agent_loop("what courses", user, "session-2", db, mock_client)
            async for event in generator:
                events.append(event)

            types = [event["type"] for event in events]
            assert "tool_call" in types
            assert "tool_result" in types
            assert "text_delta" in types
            assert "text" in types
            assert "done" in types


@pytest.mark.asyncio
async def test_recall_memory_text_response_includes_rag_metadata(setup_db):
    mock_client = AsyncMock()
    call_count = 0

    def mock_chat_completion_stream(client, messages, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_memory",
                            "type": "function",
                            "function": {"name": "recall_memory", "arguments": '{"query":"高数"}'},
                        }
                    ],
                }
            )
        return stream_response_chunks(
            response={"role": "assistant", "content": "我记得你更适合晚上复习高数。"},
            deltas=["我记得你", "更适合晚上复习高数。"],
        )

    with patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream):
        async with TestSession() as db:
            user = User(id="u-rag", username="rag", hashed_password="x")
            db.add(user)
            await db.commit()
            await create_memory(db, user.id, "preference", "高数复习优先安排在晚上")

            events = []
            generator = run_agent_loop("我高数一般什么时候复习更好？", user, "session-rag", db, mock_client)
            async for event in generator:
                events.append(event)

            text_delta = next(event for event in events if event["type"] == "text_delta")
            text_event = next(event for event in events if event["type"] == "text")

            assert text_delta["answer_kind"] == "rag"
            assert text_event["answer_kind"] == "rag"
            assert text_event["grounding"]["kind"] == "memory"
            assert text_event["grounding"]["label"] == "基于长期记忆"
            assert text_event["grounding"]["items"] == [
                {"label": "偏好", "text": "高数复习优先安排在晚上"}
            ]


@pytest.mark.asyncio
async def test_streamed_text_emits_delta_before_final_text(setup_db):
    mock_client = AsyncMock()

    with patch("app.agent.loop.chat_completion_stream") as mock_chat_completion_stream:
        mock_chat_completion_stream.return_value = stream_response_chunks(
            response={"role": "assistant", "content": "Streaming works."},
            deltas=["Streaming ", "works."],
        )

        async with TestSession() as db:
            user = User(id="u2b", username="test2b", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            generator = run_agent_loop("check stream", user, "session-2b", db, mock_client)
            async for event in generator:
                events.append(event)

            first_delta_index = next(i for i, event in enumerate(events) if event["type"] == "text_delta")
            final_text_index = next(i for i, event in enumerate(events) if event["type"] == "text")
            assert first_delta_index < final_text_index
            assert events[final_text_index]["content"] == "Streaming works."


@pytest.mark.asyncio
async def test_plain_chat_streams_delta_before_response_finishes(setup_db):
    mock_client = AsyncMock()
    allow_response = asyncio.Event()

    with patch("app.agent.loop.chat_completion_stream") as mock_chat_completion_stream:
        mock_chat_completion_stream.return_value = gated_stream_response_chunks(
            response={"role": "assistant", "content": "你好，我在。"},
            allow_response=allow_response,
            deltas=["你好，"],
        )

        async with TestSession() as db:
            user = User(id="u2b-live", username="test2b-live", hashed_password="x")
            db.add(user)
            await db.commit()

            generator = run_agent_loop("你好", user, "session-2b-live", db, mock_client)
            first_event_task = asyncio.create_task(generator.__anext__())
            done, _ = await asyncio.wait(
                {first_event_task},
                timeout=FIRST_STREAM_DELTA_TIMEOUT_SECONDS,
            )
            if not done:
                allow_response.set()
                await first_event_task
                pytest.fail("text_delta should be emitted before the final response payload arrives")

            first_event = first_event_task.result()
            assert first_event["type"] == "text_delta"
            assert first_event["delta"] == "你好，"

            allow_response.set()
            events = [first_event]
            async for event in generator:
                events.append(event)

            final_text = next(event for event in events if event["type"] == "text")
            assert final_text["message_id"] == first_event["message_id"]
            assert final_text["content"] == "你好，我在。"


@pytest.mark.asyncio
async def test_rag_runtime_hint_streams_delta_before_response_finishes(setup_db):
    mock_client = AsyncMock()
    allow_response = asyncio.Event()

    with patch("app.agent.loop.chat_completion_stream") as mock_chat_completion_stream:
        mock_chat_completion_stream.return_value = gated_stream_response_chunks(
            response={"role": "assistant", "content": "改革开放始于 1978 年。"},
            allow_response=allow_response,
            deltas=["改革开放"],
        )

        async with TestSession() as db:
            user = User(id="u2b-rag-live", username="test2b-rag-live", hashed_password="x")
            db.add(user)
            await db.commit()

            generator = run_agent_loop(
                "改革开放是什么时候开始的",
                user,
                "session-2b-rag-live",
                db,
                mock_client,
                runtime_hints=["RAG 检索上下文：改革开放始于 1978 年。"],
            )
            first_event_task = asyncio.create_task(generator.__anext__())
            done, _ = await asyncio.wait(
                {first_event_task},
                timeout=FIRST_STREAM_DELTA_TIMEOUT_SECONDS,
            )
            if not done:
                allow_response.set()
                await first_event_task
                pytest.fail("RAG text_delta should be emitted before the final response payload arrives")

            first_event = first_event_task.result()
            assert first_event["type"] == "text_delta"
            assert first_event["delta"] == "改革开放"

            allow_response.set()
            events = [first_event]
            async for event in generator:
                events.append(event)

            final_text = next(event for event in events if event["type"] == "text")
            assert final_text["message_id"] == first_event["message_id"]
            assert final_text["content"] == "改革开放始于 1978 年。"


@pytest.mark.asyncio
async def test_streaming_preamble_is_not_emitted_when_response_uses_tool_calls(setup_db):
    mock_client = AsyncMock()
    call_count = 0

    def mock_chat_completion_stream(client, messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": "让我先查一下你的课表。",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "list_courses", "arguments": "{}"},
                        }
                    ],
                },
                deltas=["让我先", "查一下你的课表。"],
            )
        return stream_response_chunks(
            response={"role": "assistant", "content": "已经找到你的课表。"},
        )

    with patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream):
        async with TestSession() as db:
            user = User(id="u2c", username="test2c", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            generator = run_agent_loop("帮我看一下现在的课表", user, "session-2c", db, mock_client)
            async for event in generator:
                events.append(event)

            assert not any(event["type"] == "text_delta" for event in events)
            assert any(event["type"] == "tool_call" and event["name"] == "list_courses" for event in events)
            assert any(event["type"] == "tool_result" and event["name"] == "list_courses" for event in events)
            final_text = next(event for event in events if event["type"] == "text")
            assert final_text["content"] == "已经找到你的课表。"


@pytest.mark.asyncio
async def test_ask_user_event_preserves_event_type(setup_db):
    """ask_user events expose event type separately from confirm/select/review mode."""
    mock_client = AsyncMock()
    call_count = 0

    def mock_chat_completion_stream(client, messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "ask_user",
                                "arguments": '{"question": "Confirm?", "type": "confirm", "options": ["Yes", "No"]}',
                            },
                        }
                    ],
                }
            )
        return stream_response_chunks(response={"role": "assistant", "content": "Continue."})

    with patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream):
        async with TestSession() as db:
            user = User(id="u3", username="test3", hashed_password="x")
            db.add(user)
            await db.commit()

            generator = run_agent_loop("help me", user, "session-3", db, mock_client)
            event = await generator.__anext__()
            assert event["type"] == "tool_call"

            ask_event = await generator.__anext__()
            assert ask_event["type"] == "ask_user"
            assert ask_event["ask_type"] == "confirm"


@pytest.mark.asyncio
async def test_ask_user_without_options_or_data_defaults_to_review(setup_db):
    """ask_user confirm without options/data should degrade to free-text review mode."""
    mock_client = AsyncMock()
    call_count = 0

    def mock_chat_completion_stream(client, messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "ask_user",
                                "arguments": '{"question": "Provide period times", "type": "confirm"}',
                            },
                        }
                    ],
                }
            )
        return stream_response_chunks(response={"role": "assistant", "content": "Received."})

    with patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream):
        async with TestSession() as db:
            user = User(id="u4", username="test4", hashed_password="x")
            db.add(user)
            await db.commit()

            generator = run_agent_loop("help me", user, "session-4", db, mock_client)
            event = await generator.__anext__()
            assert event["type"] == "tool_call"

            ask_event = await generator.__anext__()
            assert ask_event["type"] == "ask_user"
            assert ask_event["ask_type"] == "review"


@pytest.mark.asyncio
async def test_consecutive_ask_user_violation_is_not_sent_to_user(setup_db):
    mock_client = AsyncMock()
    llm_call_count = 0

    def mock_chat_completion_stream(client, messages, tools=None):
        nonlocal llm_call_count
        llm_call_count += 1
        if llm_call_count == 1:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_ask_1",
                            "type": "function",
                            "function": {
                                "name": "ask_user",
                                "arguments": '{"question": "Please confirm the parsed schedule.", "type": "review"}',
                            },
                        },
                        {
                            "id": "call_ask_2",
                            "type": "function",
                            "function": {
                                "name": "ask_user",
                                "arguments": '{"question": "Please confirm again.", "type": "review"}',
                            },
                        },
                        {
                            "id": "call_list",
                            "type": "function",
                            "function": {"name": "list_courses", "arguments": "{}"},
                        },
                    ],
                }
            )

        internal_guardrail_messages = [
            str(message.get("content") or "")
            for message in messages
            if message.get("role") == "tool"
        ]
        assert any("不能连续两次调用 ask_user" in content for content in internal_guardrail_messages)
        return stream_response_chunks(response={"role": "assistant", "content": "Recovered without surfacing an error."})

    with patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream):
        async with TestSession() as db:
            user = User(id="u5", username="test5", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            generator = run_agent_loop("please import this schedule", user, "session-5", db, mock_client)

            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user":
                        event = await generator.asend("确认")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            assert not any(event["type"] == "error" for event in events)
            assert any(event["type"] == "tool_call" and event["name"] == "list_courses" for event in events)
            assert any(event["type"] == "tool_result" and event["name"] == "list_courses" for event in events)
            assert any(event["type"] == "text" for event in events)
            assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_course_merge_shortcut_collapses_duplicate_courses_without_llm(setup_db):
    mock_client = AsyncMock()

    with patch(
        "app.agent.loop.chat_completion_stream",
        side_effect=AssertionError("LLM should not be called for local course merge shortcut"),
    ), patch(
        "app.agent.loop.chat_completion",
        side_effect=AssertionError("LLM fallback should not be called for local course merge shortcut"),
    ):
        async with TestSession() as db:
            user = User(id="u7", username="test7", hashed_password="x")
            db.add(user)
            db.add_all(
                [
                    Course(
                        id="course-wrong-rpa",
                        user_id="u7",
                        name="机器人程序动化",
                        weekday=3,
                        start_time="10:20",
                        end_time="11:55",
                    ),
                    Course(
                        id="course-right-rpa",
                        user_id="u7",
                        name="机器人流程自动化",
                        weekday=3,
                        start_time="10:20",
                        end_time="11:55",
                    ),
                    Course(
                        id="course-wrong-llm",
                        user_id="u7",
                        name="大型微调技术",
                        weekday=4,
                        start_time="14:10",
                        end_time="15:45",
                    ),
                    Course(
                        id="course-right-llm",
                        user_id="u7",
                        name="大模型微调技术",
                        weekday=4,
                        start_time="14:10",
                        end_time="15:45",
                    ),
                ]
            )
            await db.commit()

            generator = run_agent_loop(
                "你直接帮我优化成一门课吧，我现在日历里看还是两门课",
                user,
                "session-7",
                db,
                mock_client,
            )

            first_event = await generator.__anext__()
            assert first_event["type"] == "ask_user"
            assert "哪两门" in first_event["question"]

            events = [first_event]
            event = await generator.asend(
                "就是机器人程序动化和机器人流程自动化还有大型微调技术和大模型微调技术"
            )
            while True:
                events.append(event)
                if event["type"] == "ask_user":
                    event = await generator.asend("确认")
                    continue
                try:
                    event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            tool_calls = [event["name"] for event in events if event["type"] == "tool_call"]
            assert tool_calls.count("list_courses") == 1
            assert tool_calls.count("delete_course") == 2
            assert "update_course" not in tool_calls
            assert any(event["type"] == "text" for event in events)
            assert events[-1]["type"] == "done"

            result = await db.execute(
                select(Course).where(Course.user_id == "u7").order_by(Course.start_time, Course.name)
            )
            remaining_courses = list(result.scalars().all())
            assert [course.name for course in remaining_courses] == [
                "机器人流程自动化",
                "大模型微调技术",
            ]


@pytest.mark.asyncio
async def test_course_merge_shortcut_preserves_distinct_week_patterns(setup_db):
    mock_client = AsyncMock()

    with patch(
        "app.agent.loop.chat_completion_stream",
        side_effect=AssertionError("LLM should not be called for local course merge shortcut"),
    ), patch(
        "app.agent.loop.chat_completion",
        side_effect=AssertionError("LLM fallback should not be called for local course merge shortcut"),
    ):
        async with TestSession() as db:
            user = User(id="u7b", username="test7b", hashed_password="x")
            db.add(user)
            db.add_all(
                [
                    Course(
                        id="course-wrong-even",
                        user_id="u7b",
                        name="机器人程序动化",
                        weekday=3,
                        start_time="10:20",
                        end_time="11:55",
                        week_pattern="even",
                    ),
                    Course(
                        id="course-right-even",
                        user_id="u7b",
                        name="机器人流程自动化",
                        weekday=3,
                        start_time="10:20",
                        end_time="11:55",
                        week_pattern="even",
                    ),
                    Course(
                        id="course-right-odd",
                        user_id="u7b",
                        name="机器人流程自动化",
                        weekday=3,
                        start_time="10:20",
                        end_time="11:55",
                        week_pattern="odd",
                    ),
                ]
            )
            await db.commit()

            generator = run_agent_loop(
                "你直接帮我优化成一门课吧，我现在日历里看还是两门课",
                user,
                "session-7b",
                db,
                mock_client,
            )

            await generator.__anext__()
            event = await generator.asend("就是机器人程序动化和机器人流程自动化")
            while True:
                if event["type"] == "ask_user":
                    event = await generator.asend("确认")
                    continue
                try:
                    event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            result = await db.execute(
                select(Course)
                .where(Course.user_id == "u7b")
                .order_by(Course.week_pattern, Course.name)
            )
            remaining_courses = list(result.scalars().all())
            assert [(course.name, course.week_pattern) for course in remaining_courses] == [
                ("机器人流程自动化", "even"),
                ("机器人流程自动化", "odd"),
            ]


@pytest.mark.asyncio
async def test_course_rename_shortcut_updates_existing_course_without_llm(setup_db):
    mock_client = AsyncMock()

    with patch(
        "app.agent.loop.chat_completion_stream",
        side_effect=AssertionError("LLM should not be called for local course rename shortcut"),
    ), patch(
        "app.agent.loop.chat_completion",
        side_effect=AssertionError("LLM fallback should not be called for local course rename shortcut"),
    ):
        async with TestSession() as db:
            user = User(id="u7c", username="test7c", hashed_password="x")
            db.add(user)
            db.add(
                Course(
                    id="course-rename-target",
                    user_id="u7c",
                    name="机器人程序动化",
                    weekday=3,
                    start_time="10:20",
                    end_time="11:55",
                    week_pattern="all",
                )
            )
            await db.commit()

            generator = run_agent_loop(
                "把课表里的机器人程序动化改成机器人流程自动化",
                user,
                "session-7c",
                db,
                mock_client,
            )

            events = []
            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user":
                        event = await generator.asend("确认")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            tool_calls = [event["name"] for event in events if event["type"] == "tool_call"]
            assert tool_calls == ["list_courses", "update_course"]
            assert any(event["type"] == "text" and "修改 1 条课程记录" in event["content"] for event in events)

            result = await db.execute(select(Course).where(Course.user_id == "u7c"))
            courses = list(result.scalars().all())
            assert len(courses) == 1
            assert courses[0].name == "机器人流程自动化"


@pytest.mark.asyncio
async def test_course_delete_shortcut_deletes_unique_course_after_confirmation(setup_db):
    mock_client = AsyncMock()

    with patch(
        "app.agent.loop.chat_completion_stream",
        side_effect=AssertionError("LLM should not be called for local course delete shortcut"),
    ), patch(
        "app.agent.loop.chat_completion",
        side_effect=AssertionError("LLM fallback should not be called for local course delete shortcut"),
    ):
        async with TestSession() as db:
            user = User(id="u7d", username="test7d", hashed_password="x")
            db.add(user)
            db.add_all(
                [
                    Course(
                        id="course-delete-target",
                        user_id="u7d",
                        name="机器人程动",
                        weekday=3,
                        start_time="10:20",
                        end_time="11:55",
                    ),
                    Course(
                        id="course-delete-other",
                        user_id="u7d",
                        name="机器人流程自动化",
                        weekday=3,
                        start_time="10:20",
                        end_time="11:55",
                    ),
                ]
            )
            await db.commit()

            generator = run_agent_loop(
                "删掉课表里的机器人程动",
                user,
                "session-7d",
                db,
                mock_client,
            )

            events = []
            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user":
                        event = await generator.asend("确认")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            tool_calls = [event["name"] for event in events if event["type"] == "tool_call"]
            assert tool_calls == ["list_courses", "delete_course"]

            result = await db.execute(select(Course).where(Course.user_id == "u7d"))
            courses = list(result.scalars().all())
            assert [course.name for course in courses] == ["机器人流程自动化"]


@pytest.mark.asyncio
async def test_course_delete_shortcut_does_not_delete_ambiguous_same_name_courses(setup_db):
    mock_client = AsyncMock()

    with patch(
        "app.agent.loop.chat_completion_stream",
        side_effect=AssertionError("LLM should not be called for local course delete shortcut"),
    ), patch(
        "app.agent.loop.chat_completion",
        side_effect=AssertionError("LLM fallback should not be called for local course delete shortcut"),
    ):
        async with TestSession() as db:
            user = User(id="u7d2", username="test7d2", hashed_password="x")
            db.add(user)
            db.add_all(
                [
                    Course(
                        id="course-delete-ambiguous-a",
                        user_id="u7d2",
                        name="高等数学",
                        weekday=1,
                        start_time="08:30",
                        end_time="10:15",
                    ),
                    Course(
                        id="course-delete-ambiguous-b",
                        user_id="u7d2",
                        name="高等数学",
                        weekday=3,
                        start_time="10:20",
                        end_time="11:55",
                    ),
                ]
            )
            await db.commit()

            events = []
            generator = run_agent_loop(
                "删除课表里的高等数学",
                user,
                "session-7d2",
                db,
                mock_client,
            )
            async for event in generator:
                events.append(event)

            tool_calls = [event["name"] for event in events if event["type"] == "tool_call"]
            assert tool_calls == ["list_courses"]
            assert not any(event["type"] == "ask_user" for event in events)
            assert any(event["type"] == "text" and "匹配到多条同名课程" in event["content"] for event in events)

            result = await db.execute(select(Course).where(Course.user_id == "u7d2").order_by(Course.weekday))
            courses = list(result.scalars().all())
            assert [(course.name, course.weekday) for course in courses] == [("高等数学", 1), ("高等数学", 3)]


@pytest.mark.asyncio
async def test_course_maintenance_shortcut_does_not_write_when_target_missing(setup_db):
    mock_client = AsyncMock()

    with patch(
        "app.agent.loop.chat_completion_stream",
        side_effect=AssertionError("LLM should not be called for local course maintenance shortcut"),
    ), patch(
        "app.agent.loop.chat_completion",
        side_effect=AssertionError("LLM fallback should not be called for local course maintenance shortcut"),
    ):
        async with TestSession() as db:
            user = User(id="u7e", username="test7e", hashed_password="x")
            db.add(user)
            db.add(
                Course(
                    id="course-existing-only",
                    user_id="u7e",
                    name="机器人流程自动化",
                    weekday=3,
                    start_time="10:20",
                    end_time="11:55",
                )
            )
            await db.commit()

            events = []
            generator = run_agent_loop(
                "把课表里的不存在课程改成机器人流程自动化",
                user,
                "session-7e",
                db,
                mock_client,
            )
            async for event in generator:
                events.append(event)

            tool_calls = [event["name"] for event in events if event["type"] == "tool_call"]
            assert tool_calls == ["list_courses"]
            assert not any(event["type"] == "ask_user" for event in events)
            assert any(event["type"] == "text" and "没有找到" in event["content"] for event in events)

            result = await db.execute(select(Course).where(Course.user_id == "u7e"))
            courses = list(result.scalars().all())
            assert len(courses) == 1
            assert courses[0].name == "机器人流程自动化"


@pytest.mark.asyncio
async def test_continue_message_can_reuse_persisted_list_course_summary(setup_db):
    mock_client = AsyncMock()
    llm_call_count = 0
    session_id = "session-delete-continue"
    target_course_id = "course-target"

    def mock_chat_completion_stream(client, messages, tools=None):
        nonlocal llm_call_count
        llm_call_count += 1
        if llm_call_count == 1:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_list",
                            "type": "function",
                            "function": {"name": "list_courses", "arguments": "{}"},
                        }
                    ],
                }
            )
        if llm_call_count == 2:
            return stream_response_chunks(
                response={"role": "assistant", "content": "Found matching course options."},
                deltas=["Found matching ", "course options."],
            )
        if llm_call_count == 3:
            summaries = [
                str(message.get("content") or "")
                for message in messages
                if message.get("role") == "assistant"
                and str(message.get("content") or "").startswith("[TOOL_SUMMARY:list_courses:v1] ")
            ]
            assert summaries, "second turn did not include list_courses summary"
            latest_summary = summaries[-1]
            assert target_course_id in latest_summary
            assert "Hall-305" in latest_summary
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_delete",
                            "type": "function",
                            "function": {
                                "name": "delete_course",
                                "arguments": '{"course_id": "course-target"}',
                            },
                        }
                    ],
                }
            )
        return stream_response_chunks(
            response={"role": "assistant", "content": "Deleted the Hall-305 course."},
            deltas=["Deleted ", "the Hall-305 course."],
        )

    with patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream):
        async with TestSession() as db:
            user = User(id="u6", username="test6", hashed_password="x")
            db.add(user)
            db.add_all(
                [
                    Course(
                        id=target_course_id,
                        user_id="u6",
                        name="NLP",
                        location="Hall-305",
                        weekday=3,
                        start_time="08:30",
                        end_time="10:05",
                    ),
                    Course(
                        id="course-other",
                        user_id="u6",
                        name="NLP",
                        location="Hall-324",
                        weekday=4,
                        start_time="08:30",
                        end_time="10:05",
                    ),
                ]
            )
            await db.commit()

            first_round_events = []
            generator = run_agent_loop(
                "Please delete NLP in Hall-305",
                user,
                session_id,
                db,
                mock_client,
            )
            async for event in generator:
                first_round_events.append(event)

            second_round_events = []
            generator = run_agent_loop("continue", user, session_id, db, mock_client)
            async for event in generator:
                second_round_events.append(event)

            first_types = [event["type"] for event in first_round_events]
            assert first_types[:2] == ["tool_call", "tool_result"]
            assert "text_delta" in first_types
            assert first_types[-2:] == ["text", "done"]

            second_types = [event["type"] for event in second_round_events]
            assert "tool_call" in second_types
            delete_call = next(
                event
                for event in second_round_events
                if event["type"] == "tool_call" and event["name"] == "delete_course"
            )
            assert delete_call["args"] == {"course_id": target_course_id}

            message_result = await db.execute(
                select(ConversationMessage)
                .where(ConversationMessage.session_id == session_id)
                .order_by(ConversationMessage.timestamp)
            )
            stored_messages = list(message_result.scalars().all())
            persisted_summaries = [
                message
                for message in stored_messages
                if message.role == "assistant"
                and message.is_compressed
                and message.content.startswith("[TOOL_SUMMARY:list_courses:v1] ")
            ]
            assert persisted_summaries
@pytest.mark.asyncio
async def legacy_schedule_import_shortcut_collects_missing_info_and_imports_without_llm(setup_db):
    mock_client = AsyncMock()

    with patch(
        "app.agent.loop.chat_completion_stream",
        side_effect=AssertionError("LLM should not be called for local schedule import shortcut"),
    ), patch(
        "app.agent.loop.chat_completion",
        side_effect=AssertionError("LLM fallback should not be called for local schedule import shortcut"),
    ):
        async with TestSession() as db:
            user = User(id="u8", username="test8", hashed_password="x")
            db.add(user)
            await db.commit()

            file_id = store_schedule_upload(
                user_id="u8",
                kind="spreadsheet",
                courses=[
                    {
                        "name": "楂樼瓑鏁板",
                        "teacher": "寮犺€佸笀",
                        "location": "鏁欏妤糀301",
                        "weekday": 1,
                        "period": "1-2",
                        "week_start": 1,
                        "week_end": 16,
                        "week_pattern": "all",
                        "week_text": "绗?16鍛?",
                    },
                    {
                        "name": "鑷劧璇█澶勭悊",
                        "teacher": "闇嶈€佸笀",
                        "location": "A301",
                        "weekday": 3,
                        "period": "3-4",
                        "week_start": 1,
                        "week_end": 18,
                        "week_pattern": "odd",
                        "week_text": "绗?18鍛?(鍗曞懆)",
                    },
                ],
            )

            generator = run_agent_loop(
                f"鎴戜笂浼犱簡璇捐〃鏂囦欢 file_id={file_id}锛岃瑙ｆ瀽骞跺睍绀虹‘璁ゅ崱鐗囥€?",
                user,
                "session-8",
                db,
                mock_client,
            )

            event = await generator.__anext__()
            assert event["type"] == "tool_call"
            assert event["name"] == "parse_schedule"
            assert event["args"] == {"file_id": file_id}

            event = await generator.__anext__()
            assert event["type"] == "tool_result"
            assert event["result"]["status"] == "need_period_times"

            ask_event = await generator.__anext__()
            assert ask_event["type"] == "ask_user"
            assert ask_event["ask_type"] == "review"
            assert ask_event["options"] == []
            assert "missing_periods" not in ask_event["question"]
            assert "missing_semester_fields" not in ask_event["question"]
            assert "瀛︽湡寮€濮嬫棩鏈?" in ask_event["question"]
            assert "1-2" in ask_event["question"]
            assert "3-4" in ask_event["question"]

            event = await generator.asend("1-2鑺?08:30-10:15锛?-4鑺?10:20-11:55")
            assert event["type"] == "tool_call"
            assert event["name"] == "save_period_times"

            event = await generator.__anext__()
            assert event["type"] == "tool_result"
            assert event["result"]["status"] == "need_period_times"
            assert event["result"]["missing_periods"] == []
            assert "semester_start_date" in event["result"]["missing_semester_fields"]
            assert "term_total_weeks" in event["result"]["missing_semester_fields"]

            ask_event = await generator.__anext__()
            assert ask_event["type"] == "ask_user"
            assert ask_event["ask_type"] == "review"
            assert ask_event["options"] == []
            assert "瀛︽湡寮€濮嬫棩鏈?" in ask_event["question"]
            assert "1-2" not in ask_event["question"]
            assert "3-4" not in ask_event["question"]

            event = await generator.asend("2026-03-02 杩欏鏈熶竴鍏?18鍛?")
            assert event["type"] == "tool_call"
            assert event["name"] == "save_period_times"

            event = await generator.__anext__()
            assert event["type"] == "tool_result"
            assert event["result"]["status"] == "ready"
            assert event["result"]["courses"][0]["start_time"] == "08:30"
            assert event["result"]["courses"][0]["end_time"] == "10:15"
            assert event["result"]["courses"][1]["start_time"] == "10:20"
            assert event["result"]["courses"][1]["end_time"] == "11:55"
            assert event["result"]["courses"][1]["week_pattern"] == "odd"

            review_event = await generator.__anext__()
            assert review_event["type"] == "ask_user"
            assert review_event["ask_type"] == "review"
            assert review_event["options"] == ["纭", "鍙栨秷"]
            assert review_event["data"]["count"] == 2
            assert len(review_event["data"]["courses"]) == 2
            assert review_event["data"]["courses"][1]["week_pattern"] == "odd"

            event = await generator.asend("纭")
            assert event["type"] == "tool_call"
            assert event["name"] == "bulk_import_courses"

            event = await generator.__anext__()
            assert event["type"] == "tool_result"
            assert event["result"]["status"] == "imported"
            assert event["result"]["count"] == 2

            text_event = await generator.__anext__()
            assert text_event["type"] == "text"
            assert "瀵煎叆" in text_event["content"]

            done_event = await generator.__anext__()
            assert done_event["type"] == "done"

            result = await db.execute(
                select(Course).where(Course.user_id == "u8").order_by(Course.name)
            )
            imported_courses = list(result.scalars().all())
            assert [(course.name, course.start_time, course.end_time, course.week_pattern) for course in imported_courses] == [
                ("楂樼瓑鏁板", "08:30", "10:15", "all"),
                ("鑷劧璇█澶勭悊", "10:20", "11:55", "odd"),
            ]


@pytest.mark.asyncio
async def test_schedule_import_shortcut_handles_empty_image_parse_without_review_card(setup_db):
    mock_client = AsyncMock()

    with patch(
        "app.agent.loop.chat_completion_stream",
        side_effect=AssertionError("LLM should not be called for local schedule import shortcut"),
    ), patch(
        "app.agent.loop.chat_completion",
        side_effect=AssertionError("LLM fallback should not be called for local schedule import shortcut"),
    ):
        async with TestSession() as db:
            user = User(id="u-empty-image", username="empty-image", hashed_password="x")
            db.add(user)
            await db.commit()

            file_id = store_schedule_upload(
                user_id="u-empty-image",
                kind="image",
                courses=[],
                status="PARSED",
                progress=100,
                source_file_count=1,
            )

            generator = run_agent_loop(
                f"我上传了一张课表图片 file_id={file_id}，请解析并展示确认卡片。",
                user,
                "session-empty-image",
                db,
                mock_client,
            )

            event = await generator.__anext__()
            assert event["type"] == "tool_call"
            assert event["name"] == "parse_schedule_image"

            event = await generator.__anext__()
            assert event["type"] == "tool_result"
            assert event["result"]["status"] == "ready"
            assert event["result"]["count"] == 0

            text_event = await generator.__anext__()
            assert text_event["type"] == "text"
            assert "没有从这张图片里识别到课程信息" in text_event["content"]

            done_event = await generator.__anext__()
            assert done_event["type"] == "done"
