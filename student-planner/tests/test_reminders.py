import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_reminder(auth_client: AsyncClient):
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


@pytest.mark.asyncio
async def test_list_reminders(auth_client: AsyncClient):
    await auth_client.post(
        "/api/reminders/",
        json={"target_type": "task", "target_id": "fake-task-id", "remind_at": "2026-04-01T09:00:00"},
    )
    response = await auth_client.get("/api/reminders/")
    assert response.status_code == 200
    assert len(response.json()) >= 1


@pytest.mark.asyncio
async def test_delete_reminder(auth_client: AsyncClient):
    create = await auth_client.post(
        "/api/reminders/",
        json={"target_type": "task", "target_id": "fake-id", "remind_at": "2026-04-02T10:00:00"},
    )
    reminder_id = create.json()["id"]
    response = await auth_client.delete(f"/api/reminders/{reminder_id}")
    assert response.status_code == 204