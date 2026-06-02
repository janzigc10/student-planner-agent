import asyncio
import io
from pathlib import Path
from unittest.mock import AsyncMock

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
    async def fake_parse_schedule_image(
        image_bytes: bytes,
        mime_type: str,
        fallback_week_number: int | None = None,
        prefer_parity_from_week_hint: bool = False,
    ) -> list[RawCourse]:
        if image_bytes == b"img-1":
            return [_course("image-course-1")]
        if image_bytes == b"img-2":
            return [_course("image-course-2")]
        raise AssertionError(f"unexpected image payload: {image_bytes!r}")

    monkeypatch.setattr("app.agent.schedule_ocr.parse_schedule_image", fake_parse_schedule_image)
    monkeypatch.setattr("app.agent.schedule_ocr.detect_schedule_week", AsyncMock(return_value=None))

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
    assert data["status"] == "processing"
    assert data["count"] == 0
    assert data["courses"] == []

    status_payload: dict | None = None
    for _ in range(50):
        status_response = await auth_client.get(f"/api/schedule/upload/{data['file_id']}")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        if status_payload["status"] == "PARSED":
            break
        await asyncio.sleep(0.01)

    assert status_payload is not None
    assert status_payload["status"] == "PARSED"
    assert status_payload["count"] == 2
    assert [course["name"] for course in status_payload["courses"]] == [
        "image-course-1",
        "image-course-2",
    ]


@pytest.mark.asyncio
async def test_upload_multiple_images_merges_odd_even_into_all_weeks(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_parse_schedule_image(
        image_bytes: bytes,
        mime_type: str,
        fallback_week_number: int | None = None,
        prefer_parity_from_week_hint: bool = False,
    ) -> list[RawCourse]:
        if image_bytes == b"img-odd":
            return [
                RawCourse(
                    name="natural-language-processing",
                    teacher=None,
                    location="room-301",
                    weekday=3,
                    period="1-2",
                    week_start=1,
                    week_end=18,
                    week_pattern="odd",
                    week_text="第1-18周(单周)",
                )
            ]
        if image_bytes == b"img-even":
            return [
                RawCourse(
                    name="natural-language-processing",
                    teacher=None,
                    location="room-301",
                    weekday=3,
                    period="1-2",
                    week_start=1,
                    week_end=18,
                    week_pattern="even",
                    week_text="第1-18周(双周)",
                )
            ]
        raise AssertionError(f"unexpected image payload: {image_bytes!r}")

    monkeypatch.setattr("app.agent.schedule_ocr.parse_schedule_image", fake_parse_schedule_image)
    monkeypatch.setattr("app.agent.schedule_ocr.detect_schedule_week", AsyncMock(return_value=None))

    response = await auth_client.post(
        "/api/schedule/upload",
        files=[
            ("file", ("odd.png", io.BytesIO(b"img-odd"), "image/png")),
            ("file", ("even.jpg", io.BytesIO(b"img-even"), "image/jpeg")),
        ],
    )
    assert response.status_code == 200
    upload = response.json()

    status_payload: dict | None = None
    for _ in range(50):
        status_response = await auth_client.get(f"/api/schedule/upload/{upload['file_id']}")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        if status_payload["status"] == "PARSED":
            break
        await asyncio.sleep(0.01)

    assert status_payload is not None
    assert status_payload["status"] == "PARSED"
    assert status_payload["count"] == 1
    course = status_payload["courses"][0]
    assert course["week_start"] == 1
    assert course["week_end"] == 18
    assert course["week_pattern"] == "all"
    assert course["week_text"] == "第1-18周"


@pytest.mark.asyncio
async def test_upload_image_status_reports_failed_parse(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_parse_schedule_image(
        image_bytes: bytes,
        mime_type: str,
        fallback_week_number: int | None = None,
        prefer_parity_from_week_hint: bool = False,
    ) -> list[RawCourse]:
        raise RuntimeError("vision parser down")

    monkeypatch.setattr(
        "app.agent.schedule_ocr.parse_schedule_image",
        failing_parse_schedule_image,
    )
    monkeypatch.setattr("app.agent.schedule_ocr.detect_schedule_week", AsyncMock(return_value=None))

    response = await auth_client.post(
        "/api/schedule/upload",
        files=[("file", ("one.png", io.BytesIO(b"img-1"), "image/png"))],
    )
    assert response.status_code == 200
    upload = response.json()

    status_payload: dict | None = None
    for _ in range(50):
        status_response = await auth_client.get(f"/api/schedule/upload/{upload['file_id']}")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        if status_payload["status"] == "FAILED":
            break
        await asyncio.sleep(0.01)

    assert status_payload is not None
    assert status_payload["status"] == "FAILED"
    assert status_payload["error"] == "vision parser down"


@pytest.mark.asyncio
async def test_upload_non_schedule_image_can_finish_with_zero_courses(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_parse_schedule_image(
        image_bytes: bytes,
        mime_type: str,
        fallback_week_number: int | None = None,
        prefer_parity_from_week_hint: bool = False,
    ) -> list[RawCourse]:
        assert image_bytes == b"resume-image"
        return []

    monkeypatch.setattr("app.agent.schedule_ocr.parse_schedule_image", fake_parse_schedule_image)
    monkeypatch.setattr("app.agent.schedule_ocr.detect_schedule_week", AsyncMock(return_value=None))

    response = await auth_client.post(
        "/api/schedule/upload",
        files=[("file", ("resume.png", io.BytesIO(b"resume-image"), "image/png"))],
    )
    assert response.status_code == 200
    upload = response.json()
    assert upload["status"] == "processing"

    status_payload: dict | None = None
    for _ in range(50):
        status_response = await auth_client.get(f"/api/schedule/upload/{upload['file_id']}")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        if status_payload["status"] == "PARSED":
            break
        await asyncio.sleep(0.01)

    assert status_payload is not None
    assert status_payload["status"] == "PARSED"
    assert status_payload["count"] == 0
    assert status_payload["courses"] == []
    assert status_payload["progress"] == 100


@pytest.mark.asyncio
async def test_upload_status_returns_404_when_file_id_is_unknown(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/schedule/upload/missing-id")
    assert response.status_code == 404


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
async def test_upload_invalid_spreadsheet_returns_readable_error(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/schedule/upload",
        files={
            "file": (
                "schedule.xls",
                io.BytesIO(b"not-a-real-spreadsheet"),
                "application/vnd.ms-excel",
            )
        },
    )

    assert response.status_code == 400
    assert "课表文件无法解析" in response.json()["detail"]


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
