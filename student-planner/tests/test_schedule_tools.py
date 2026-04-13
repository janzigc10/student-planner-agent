import pytest

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
            preferences={
                "period_schedule": {
                    "1-2": {"start": "08:20", "end": "10:00"},
                }
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
