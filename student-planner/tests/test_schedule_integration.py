from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.agent.tool_executor import execute_tool
from app.models.course import Course
from app.services.period_converter import DEFAULT_SCHEDULE, convert_periods
from app.services.schedule_parser import parse_excel_schedule

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_schedule.xlsx"


@pytest.mark.asyncio
async def test_full_excel_import_flow(auth_client: AsyncClient) -> None:
    with open(FIXTURE_PATH, "rb") as fixture:
        upload_response = await auth_client.post(
            "/api/schedule/upload",
            files={
                "file": (
                    "schedule.xlsx",
                    fixture,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    assert upload_response.status_code == 200
    parsed = upload_response.json()
    assert parsed["count"] == 6

    courses_for_import = []
    for raw in parsed["courses"]:
        times = convert_periods(raw["period"], DEFAULT_SCHEDULE)
        assert times is not None, f"Failed to convert period {raw['period']}"
        courses_for_import.append(
            {
                "name": raw["name"],
                "teacher": raw["teacher"],
                "location": raw["location"],
                "weekday": raw["weekday"],
                "start_time": times["start_time"],
                "end_time": times["end_time"],
                "week_start": raw["week_start"],
                "week_end": raw["week_end"],
            }
        )

    from tests.conftest import TestSession

    async with TestSession() as db:
        me_response = await auth_client.get("/api/auth/me")
        user_id = me_response.json()["id"]

        result = await execute_tool(
            "bulk_import_courses",
            {"courses": courses_for_import},
            db=db,
            user_id=user_id,
        )
        assert result["status"] == "imported"
        assert result["count"] == 6

        db_courses = await db.execute(select(Course).where(Course.user_id == user_id))
        courses = db_courses.scalars().all()
        assert len(courses) == 6

        gaoshu = next(course for course in courses if course.name == "高等数学")
        assert gaoshu.start_time == "08:00"
        assert gaoshu.end_time == "09:40"
        assert gaoshu.weekday == 1
        assert gaoshu.week_start == 1
        assert gaoshu.week_end == 16


@pytest.mark.asyncio
async def test_period_conversion_all_fixture_courses() -> None:
    courses = parse_excel_schedule(FIXTURE_PATH)
    for course in courses:
        times = convert_periods(course.period, DEFAULT_SCHEDULE)
        assert times is not None, f"Cannot convert period '{course.period}' for {course.name}"
        assert ":" in times["start_time"]
        assert ":" in times["end_time"]