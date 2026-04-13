import io
from pathlib import Path

import pytest
from httpx import AsyncClient

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_schedule.xlsx"


@pytest.mark.asyncio
async def test_upload_excel_returns_courses(auth_client: AsyncClient) -> None:
    with open(FIXTURE_PATH, "rb") as fixture:
        response = await auth_client.post(
            "/api/schedule/upload",
            files={
                "file": (
                    "schedule.xlsx",
                    fixture,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert "courses" in data
    assert data["kind"] == "spreadsheet"
    assert data["file_id"]
    assert len(data["courses"]) == 6
    names = {course["name"] for course in data["courses"]}
    assert "高等数学" in names


@pytest.mark.asyncio
async def test_upload_excel_includes_period_field(auth_client: AsyncClient) -> None:
    with open(FIXTURE_PATH, "rb") as fixture:
        response = await auth_client.post(
            "/api/schedule/upload",
            files={
                "file": (
                    "schedule.xlsx",
                    fixture,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    data = response.json()
    gaoshu = next(course for course in data["courses"] if course["name"] == "高等数学")
    assert gaoshu["period"] == "1-2"
    assert gaoshu["weekday"] == 1


@pytest.mark.asyncio
async def test_upload_unsupported_format(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/schedule/upload",
        files={"file": ("schedule.txt", io.BytesIO(b"not a schedule"), "text/plain")},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/api/schedule/upload",
        files={
            "file": (
                "schedule.xlsx",
                io.BytesIO(b"fake"),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 403
