import io
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.services.schedule_parser import RawCourse

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_schedule.xlsx"


def _course(name: str, weekday: int = 1, period: str = "1-2") -> RawCourse:
    return RawCourse(
        name=name,
        teacher="Teacher",
        location="Room 101",
        weekday=weekday,
        period=period,
        week_start=1,
        week_end=16,
    )


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
    assert data["source_file_count"] == 1


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
async def test_upload_multiple_images_merges_courses(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_parse_schedule_image(image_bytes: bytes, mime_type: str) -> list[RawCourse]:
        if image_bytes == b"img-1":
            return [_course("image-course-1")]
        if image_bytes == b"img-2":
            return [_course("image-course-2")]
        raise AssertionError(f"unexpected image payload: {image_bytes!r}")

    monkeypatch.setattr("app.agent.schedule_ocr.parse_schedule_image", fake_parse_schedule_image)

    response = await auth_client.post(
        "/api/schedule/upload",
        files=[
            ("file", ("one.png", io.BytesIO(b"img-1"), "image/png")),
            ("file", ("two.jpg", io.BytesIO(b"img-2"), "image/jpeg")),
        ],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["file_id"]
    assert data["kind"] == "image"
    assert data["source_file_count"] == 2
    assert data["count"] == 2
    assert [course["name"] for course in data["courses"]] == ["image-course-1", "image-course-2"]


@pytest.mark.asyncio
async def test_upload_rejects_mixed_image_and_spreadsheet(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/schedule/upload",
        files=[
            ("file", ("schedule.png", io.BytesIO(b"img"), "image/png")),
            (
                "file",
                (
                    "schedule.xlsx",
                    io.BytesIO(b"xlsx"),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            ),
        ],
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_more_than_three_images(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/schedule/upload",
        files=[
            ("file", ("1.png", io.BytesIO(b"1"), "image/png")),
            ("file", ("2.png", io.BytesIO(b"2"), "image/png")),
            ("file", ("3.png", io.BytesIO(b"3"), "image/png")),
            ("file", ("4.png", io.BytesIO(b"4"), "image/png")),
        ],
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_more_than_one_spreadsheet(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/schedule/upload",
        files=[
            (
                "file",
                (
                    "schedule-a.xlsx",
                    io.BytesIO(b"xlsx-a"),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            ),
            (
                "file",
                (
                    "schedule-b.xlsx",
                    io.BytesIO(b"xlsx-b"),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            ),
        ],
    )
    assert response.status_code == 400


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
