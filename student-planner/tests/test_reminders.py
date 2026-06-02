import pytest
from httpx import AsyncClient
from unittest.mock import patch


@pytest.mark.asyncio
@patch("app.routers.reminders.schedule_reminder_job")
async def test_create_reminder(mock_schedule, auth_client: AsyncClient):
    course = await auth_client.post(
        "/api/courses/",
        json={"name": "高等数学", "weekday": 1, "start_time": "08:00", "end_time": "09:40"},
    )
    response = await auth_client.post(
        "/api/reminders/",
        json={"target_type": "course", "target_id": course.json()["id"], "remind_at": "2026-03-30T07:45:00"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert response.json()["advance_minutes"] == 15
    mock_schedule.assert_called_once()
    assert mock_schedule.call_args.kwargs["reminder_id"] == response.json()["id"]


@pytest.mark.asyncio
async def test_list_reminders(auth_client: AsyncClient):
    await auth_client.post(
        "/api/reminders/",
        json={"target_type": "task", "target_id": "fake-task-id", "remind_at": "2026-04-01T09:00:00"},
    )
    response = await auth_client.get("/api/reminders/")
    assert response.status_code == 200
    assert len(response.json()) >= 1
    assert response.json()[0]["advance_minutes"] == 15


@pytest.mark.asyncio
@patch("app.routers.reminders.cancel_reminder_job")
async def test_delete_reminder(mock_cancel, auth_client: AsyncClient):
    create = await auth_client.post(
        "/api/reminders/",
        json={"target_type": "task", "target_id": "fake-id", "remind_at": "2026-04-02T10:00:00"},
    )
    reminder_id = create.json()["id"]
    response = await auth_client.delete(f"/api/reminders/{reminder_id}")
    assert response.status_code == 204
    mock_cancel.assert_called_once_with(reminder_id)
