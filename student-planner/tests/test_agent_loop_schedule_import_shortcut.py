from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.agent.contracts import DBWritePlan, PendingConfirmation
from app.agent.loop import run_agent_loop
from app.models.course import Course
from app.models.user import User
from app.services.schedule_upload_cache import store_schedule_upload
from tests.conftest import TestSession


@pytest.mark.asyncio
async def test_schedule_import_shortcut_collects_missing_info_and_imports_without_llm(setup_db):
    from app.agent import langgraph_loop as langgraph_runtime

    mock_client = AsyncMock()
    observed_graph_states: list[dict] = []
    original_step = langgraph_runtime.run_langgraph_schedule_import_step

    async def spy_schedule_step(state, runtime, *, node_name):
        next_state = await original_step(state, runtime, node_name=node_name)
        observed_graph_states.append(dict(next_state))
        return next_state

    with patch(
        "app.agent.loop.chat_completion_stream",
        side_effect=AssertionError("LLM should not be called for local schedule import shortcut"),
    ), patch(
        "app.agent.loop.chat_completion",
        side_effect=AssertionError("LLM fallback should not be called for local schedule import shortcut"),
    ), patch(
        "app.agent.langgraph_loop.run_langgraph_schedule_import_step",
        side_effect=spy_schedule_step,
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
                        "name": "all-course",
                        "teacher": "Teacher A",
                        "location": "Room 301",
                        "weekday": 1,
                        "period": "1-2",
                        "week_start": 1,
                        "week_end": 16,
                        "week_pattern": "all",
                        "week_text": "\u7b2c1-16\u5468",
                    },
                    {
                        "name": "odd-course",
                        "teacher": "Teacher B",
                        "location": "A301",
                        "weekday": 3,
                        "period": "3-4",
                        "week_start": 1,
                        "week_end": 18,
                        "week_pattern": "odd",
                        "week_text": "\u7b2c1-18\u5468(\u5355\u5468)",
                    },
                ],
            )

            generator = run_agent_loop(
                f"please import this schedule file_id={file_id}",
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
            assert "1-2" in ask_event["question"]
            assert "3-4" in ask_event["question"]

            event = await generator.asend("1-2节 08:30-10:15 3-4节 10:20-11:55")
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
            assert "1-2" not in ask_event["question"]
            assert "3-4" not in ask_event["question"]
            assert "2026-03-02" in ask_event["question"]

            event = await generator.asend("2026-03-02 这学期一共18周")
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
            assert review_event["options"] == ["确认", "取消"]
            assert review_event["data"]["count"] == 2
            assert len(review_event["data"]["courses"]) == 2
            assert review_event["data"]["courses"][1]["week_pattern"] == "odd"

            event = await generator.asend("确认")
            assert event["type"] == "tool_call"
            assert event["name"] == "bulk_import_courses"

            event = await generator.__anext__()
            assert event["type"] == "tool_result"
            assert event["result"]["status"] == "imported"
            assert event["result"]["count"] == 2

            text_event = await generator.__anext__()
            assert text_event["type"] == "text"
            assert text_event["content"]

            done_event = await generator.__anext__()
            assert done_event["type"] == "done"

            result = await db.execute(
                select(Course).where(Course.user_id == "u8").order_by(Course.name)
            )
            imported_courses = list(result.scalars().all())
            assert [
                (course.name, course.start_time, course.end_time, course.week_pattern)
                for course in imported_courses
            ] == [
                ("all-course", "08:30", "10:15", "all"),
                ("odd-course", "10:20", "11:55", "odd"),
            ]

    observed_schedule_states = [
        dict(state.get("schedule_import") or {}) for state in observed_graph_states
    ]
    assert [state.get("node") for state in observed_schedule_states] == [
        "schedule_parse",
        "ask_user_pause",
        "schedule_parse",
        "ask_user_pause",
        "schedule_parse",
        "ask_user_pause",
        "confirmed_write",
    ]
    assert observed_schedule_states[0]["current_result"]["status"] == "need_period_times"
    assert observed_schedule_states[2]["last_tool_name"] == "save_period_times"
    assert observed_schedule_states[2]["current_result"]["status"] == "need_period_times"
    assert observed_schedule_states[4]["last_tool_name"] == "save_period_times"
    assert observed_schedule_states[4]["current_result"]["status"] == "ready"
    assert observed_graph_states[1]["pending_ask"]["status"] == "awaiting_answer"
    assert observed_graph_states[3]["pending_ask"]["status"] == "awaiting_answer"
    assert isinstance(observed_schedule_states[5]["pending_confirmation"], PendingConfirmation)
    assert isinstance(observed_schedule_states[5]["db_write_plan"], DBWritePlan)
    assert observed_schedule_states[6]["confirmed_result"]["status"] == "imported"


@pytest.mark.asyncio
async def test_schedule_import_shortcut_prepares_confirmation_state_before_write(setup_db):
    mock_client = AsyncMock()

    with patch(
        "app.agent.loop.chat_completion_stream",
        side_effect=AssertionError("LLM should not be called for local schedule import shortcut"),
    ), patch(
        "app.agent.loop.chat_completion",
        side_effect=AssertionError("LLM fallback should not be called for local schedule import shortcut"),
    ), patch(
        "app.agent.langgraph_loop.execute_langgraph_confirmed_db_write_plan",
        new_callable=AsyncMock,
        return_value={"status": "imported", "count": 1, "courses": ["stateful-course"]},
    ) as mock_execute_confirmed:
        async with TestSession() as db:
            user = User(
                id="u8-stateful",
                username="test8-stateful",
                hashed_password="x",
                current_semester_start=date(2026, 3, 2),
                preferences={"current_term_total_weeks": 18},
            )
            db.add(user)
            await db.commit()

            file_id = store_schedule_upload(
                user_id="u8-stateful",
                kind="spreadsheet",
                courses=[
                    {
                        "name": "stateful-course",
                        "teacher": "Teacher C",
                        "location": "Room 501",
                        "weekday": 2,
                        "start_time": "14:00",
                        "end_time": "15:35",
                        "week_start": 1,
                        "week_end": 18,
                        "week_pattern": "all",
                        "week_text": "\u7b2c1-18\u5468",
                    }
                ],
            )

            generator = run_agent_loop(
                f"please import this schedule file_id={file_id}",
                user,
                "session-8-stateful",
                db,
                mock_client,
            )

            assert (await generator.__anext__())["name"] == "parse_schedule"
            parse_result_event = await generator.__anext__()
            assert parse_result_event["type"] == "tool_result"
            assert parse_result_event["result"]["status"] == "ready"

            review_event = await generator.__anext__()
            assert review_event["type"] == "ask_user"
            assert review_event["ask_type"] == "review"
            assert review_event["data"]["count"] == 1
            assert mock_execute_confirmed.await_count == 0

            before_result = await db.execute(select(Course).where(Course.user_id == "u8-stateful"))
            assert list(before_result.scalars().all()) == []

            event = await generator.asend("确认")
            assert event["type"] == "tool_call"
            assert event["name"] == "bulk_import_courses"

            event = await generator.__anext__()
            assert event["type"] == "tool_result"
            assert mock_execute_confirmed.await_count == 1
            call_kwargs = mock_execute_confirmed.await_args.kwargs
            assert isinstance(call_kwargs["pending_confirmation"], PendingConfirmation)
            assert isinstance(call_kwargs["db_write_plan"], DBWritePlan)
            assert (
                call_kwargs["pending_confirmation"].confirmation_id
                == call_kwargs["db_write_plan"].confirmation_id
            )
            assert call_kwargs["db_write_plan"].tool_name == "bulk_import_courses"


@pytest.mark.asyncio
async def test_schedule_import_shortcut_cancel_does_not_execute_write_plan(setup_db):
    mock_client = AsyncMock()

    with patch(
        "app.agent.loop.chat_completion_stream",
        side_effect=AssertionError("LLM should not be called for local schedule import shortcut"),
    ), patch(
        "app.agent.loop.chat_completion",
        side_effect=AssertionError("LLM fallback should not be called for local schedule import shortcut"),
    ), patch(
        "app.agent.langgraph_loop.execute_langgraph_confirmed_db_write_plan",
        new_callable=AsyncMock,
        side_effect=AssertionError("Cancelled schedule import should not execute its write plan"),
    ):
        async with TestSession() as db:
            user = User(
                id="u8-cancel",
                username="test8-cancel",
                hashed_password="x",
                current_semester_start=date(2026, 3, 2),
                preferences={"current_term_total_weeks": 18},
            )
            db.add(user)
            await db.commit()

            file_id = store_schedule_upload(
                user_id="u8-cancel",
                kind="spreadsheet",
                courses=[
                    {
                        "name": "cancelled-course",
                        "teacher": "Teacher D",
                        "location": "Room 601",
                        "weekday": 4,
                        "start_time": "08:30",
                        "end_time": "10:05",
                        "week_start": 1,
                        "week_end": 18,
                        "week_pattern": "all",
                        "week_text": "\u7b2c1-18\u5468",
                    }
                ],
            )

            generator = run_agent_loop(
                f"please import this schedule file_id={file_id}",
                user,
                "session-8-cancel",
                db,
                mock_client,
            )

            await generator.__anext__()
            await generator.__anext__()
            review_event = await generator.__anext__()
            assert review_event["type"] == "ask_user"

            text_event = await generator.asend("取消")
            assert text_event["type"] == "text"
            done_event = await generator.__anext__()
            assert done_event["type"] == "done"

            result = await db.execute(select(Course).where(Course.user_id == "u8-cancel"))
            assert list(result.scalars().all()) == []


@pytest.mark.asyncio
async def test_confirmed_db_write_plan_requires_matching_confirmation_state(setup_db):
    from app.agent.loop import _execute_confirmed_db_write_plan

    async with TestSession() as db:
        result = await _execute_confirmed_db_write_plan(
            pending_confirmation=None,
            db_write_plan=DBWritePlan(
                confirmation_id="missing-state",
                route="schedule_import",
                tool_name="bulk_import_courses",
                args={"courses": [{"name": "blocked"}]},
                description="blocked write",
            ),
            confirmation_answer="确认",
            db=db,
            user_id="u8-missing-state",
        )

    assert result["error"] == "Missing pending confirmation state for database write."
