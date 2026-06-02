import pytest
from datetime import date

from app.agent.tool_executor import execute_tool
from app.agent.tools import TOOL_DEFINITIONS
from app.models.user import User
from app.services.schedule_upload_cache import store_schedule_upload


def test_parse_schedule_tool_defined() -> None:
    names = [tool["function"]["name"] for tool in TOOL_DEFINITIONS]
    assert "parse_schedule" in names


def test_parse_schedule_image_tool_defined() -> None:
    names = [tool["function"]["name"] for tool in TOOL_DEFINITIONS]
    assert "parse_schedule_image" in names


def test_parse_schedule_requires_file_id() -> None:
    tool = next(tool for tool in TOOL_DEFINITIONS if tool["function"]["name"] == "parse_schedule")
    assert "file_id" in tool["function"]["parameters"]["required"]


def test_parse_schedule_image_requires_file_id() -> None:
    tool = next(
        tool for tool in TOOL_DEFINITIONS if tool["function"]["name"] == "parse_schedule_image"
    )
    assert "file_id" in tool["function"]["parameters"]["required"]


@pytest.mark.asyncio
async def test_parse_schedule_reads_cached_upload_and_converts_periods(setup_db) -> None:
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(
            id="schedule-user-1",
            username="scheduleuser",
            hashed_password="x",
            current_semester_start=date(2026, 3, 2),
            preferences={
                "period_schedule": {
                    "1-2": {"start": "08:20", "end": "10:00"},
                },
                "current_term_total_weeks": 18,
            },
        )
        db.add(user)
        await db.commit()

        file_id = store_schedule_upload(
            user_id="schedule-user-1",
            kind="spreadsheet",
            courses=[
                {
                    "name": "高等数学",
                    "teacher": "张老师",
                    "location": "教学楼A301",
                    "weekday": 1,
                    "period": "1-2",
                    "week_start": 1,
                    "week_end": 16,
                }
            ],
        )

        result = await execute_tool(
            "parse_schedule",
            {"file_id": file_id},
            db=db,
            user_id="schedule-user-1",
        )

        assert result["status"] == "ready"
        assert result["kind"] == "spreadsheet"
        assert result["courses"][0]["start_time"] == "08:20"
        assert result["courses"][0]["end_time"] == "10:00"


@pytest.mark.asyncio
async def test_parse_schedule_requires_semester_meta_when_missing(setup_db) -> None:
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(
            id="schedule-user-sem-missing",
            username="scheduleuser-sem-missing",
            hashed_password="x",
            preferences={
                "period_schedule": {
                    "1-2": {"start": "08:20", "end": "10:00"},
                }
            },
        )
        db.add(user)
        await db.commit()

        file_id = store_schedule_upload(
            user_id="schedule-user-sem-missing",
            kind="spreadsheet",
            courses=[
                {
                    "name": "高等数学",
                    "teacher": "张老师",
                    "location": "教学楼A301",
                    "weekday": 1,
                    "period": "1-2",
                    "week_start": 1,
                    "week_end": 18,
                }
            ],
        )

        result = await execute_tool(
            "parse_schedule",
            {"file_id": file_id},
            db=db,
            user_id="schedule-user-sem-missing",
        )

        assert result["status"] == "need_period_times"
        assert result["missing_periods"] == []
        assert "semester_start_date" in result["missing_semester_fields"]
        assert "term_total_weeks" in result["missing_semester_fields"]


@pytest.mark.asyncio
async def test_save_period_times_can_save_semester_meta_without_new_period_entries(setup_db) -> None:
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(
            id="schedule-user-sem-save",
            username="scheduleuser-sem-save",
            hashed_password="x",
            preferences={
                "period_schedule": {
                    "1-2": {"start": "08:20", "end": "10:00"},
                }
            },
        )
        db.add(user)
        await db.commit()

        file_id = store_schedule_upload(
            user_id="schedule-user-sem-save",
            kind="spreadsheet",
            courses=[
                {
                    "name": "高等数学",
                    "teacher": "张老师",
                    "location": "教学楼A301",
                    "weekday": 1,
                    "period": "1-2",
                    "week_start": 1,
                    "week_end": 18,
                }
            ],
            status="NEED_PERIOD_TIMES",
            missing_periods=[],
            missing_semester_fields=["semester_start_date", "term_total_weeks"],
        )

        result = await execute_tool(
            "save_period_times",
            {
                "file_id": file_id,
                "entries": [],
                "semester_start_date": "2026-03-02",
                "term_total_weeks": 16,
            },
            db=db,
            user_id="schedule-user-sem-save",
        )

        assert result["status"] == "ready"
        assert result["semester_start_date"] == "2026-03-02"
        assert result["term_total_weeks"] == 16
        assert result["courses"][0]["week_start"] == 1
        assert result["courses"][0]["week_end"] == 16

        await db.refresh(user)
        assert user.current_semester_start == date(2026, 3, 2)
        assert user.preferences is not None
        assert user.preferences.get("current_term_total_weeks") == 16


@pytest.mark.asyncio
async def test_parse_schedule_missing_file_id_returns_error(setup_db) -> None:
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="schedule-user-2", username="scheduleuser2", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await execute_tool(
            "parse_schedule",
            {"file_id": "missing"},
            db=db,
            user_id="schedule-user-2",
        )

        assert result["error"] == "Schedule upload not found"


@pytest.mark.asyncio
async def test_parse_schedule_image_returns_processing_status_when_background_parse_not_ready(
    setup_db,
) -> None:
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="schedule-user-3", username="scheduleuser3", hashed_password="x")
        db.add(user)
        await db.commit()

        file_id = store_schedule_upload(
            user_id="schedule-user-3",
            kind="image",
            courses=[],
            status="PARSING",
            progress=42,
        )

        result = await execute_tool(
            "parse_schedule_image",
            {"file_id": file_id},
            db=db,
            user_id="schedule-user-3",
        )

        assert result["status"] == "processing"
        assert result["progress"] == 42
        assert result["file_id"] == file_id


@pytest.mark.asyncio
async def test_parse_schedule_image_returns_failed_status_when_background_parse_fails(
    setup_db,
) -> None:
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="schedule-user-4", username="scheduleuser4", hashed_password="x")
        db.add(user)
        await db.commit()

        file_id = store_schedule_upload(
            user_id="schedule-user-4",
            kind="image",
            courses=[],
            status="FAILED",
            error="vision parser down",
        )

        result = await execute_tool(
            "parse_schedule_image",
            {"file_id": file_id},
            db=db,
            user_id="schedule-user-4",
        )

        assert result["status"] == "failed"
        assert result["error"] == "vision parser down"


@pytest.mark.asyncio
async def test_parse_schedule_image_empty_courses_does_not_request_semester_meta(
    setup_db,
) -> None:
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="schedule-user-empty-image", username="scheduleuser-empty", hashed_password="x")
        db.add(user)
        await db.commit()

        file_id = store_schedule_upload(
            user_id="schedule-user-empty-image",
            kind="image",
            courses=[],
            status="PARSED",
            progress=100,
        )

        result = await execute_tool(
            "parse_schedule_image",
            {"file_id": file_id},
            db=db,
            user_id="schedule-user-empty-image",
        )

        assert result["status"] == "ready"
        assert result["count"] == 0
        assert result["courses"] == []
        assert "没有从这张图片里识别到课程信息" in result["message"]
