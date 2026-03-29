import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_task(auth_client: AsyncClient):
    response = await auth_client.post(
        "/api/tasks/",
        json={
            "title": "高数 - 极限复习",
            "scheduled_date": "2026-03-30",
            "start_time": "10:00",
            "end_time": "12:00",
        },
    )
    assert response.status_code == 201
    assert response.json()["title"] == "高数 - 极限复习"
    assert response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_time_conflict(auth_client: AsyncClient):
    await auth_client.post(
        "/api/tasks/",
        json={"title": "线代复习", "scheduled_date": "2026-03-31", "start_time": "14:00", "end_time": "16:00"},
    )
    response = await auth_client.post(
        "/api/tasks/",
        json={"title": "概率论复习", "scheduled_date": "2026-03-31", "start_time": "15:00", "end_time": "17:00"},
    )
    assert response.status_code == 409
    assert "conflict" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_no_conflict_different_day(auth_client: AsyncClient):
    await auth_client.post(
        "/api/tasks/",
        json={"title": "Task A", "scheduled_date": "2026-04-01", "start_time": "10:00", "end_time": "12:00"},
    )
    response = await auth_client.post(
        "/api/tasks/",
        json={"title": "Task B", "scheduled_date": "2026-04-02", "start_time": "10:00", "end_time": "12:00"},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_list_tasks_date_filter(auth_client: AsyncClient):
    await auth_client.post(
        "/api/tasks/",
        json={"title": "Early", "scheduled_date": "2026-03-28", "start_time": "09:00", "end_time": "10:00"},
    )
    await auth_client.post(
        "/api/tasks/",
        json={"title": "Late", "scheduled_date": "2026-04-10", "start_time": "09:00", "end_time": "10:00"},
    )
    response = await auth_client.get("/api/tasks/?date_from=2026-04-01&date_to=2026-04-30")
    assert response.status_code == 200
    titles = [task["title"] for task in response.json()]
    assert "Late" in titles
    assert "Early" not in titles


@pytest.mark.asyncio
async def test_update_task_status(auth_client: AsyncClient):
    create = await auth_client.post(
        "/api/tasks/",
        json={"title": "Complete me", "scheduled_date": "2026-04-03", "start_time": "08:00", "end_time": "09:00"},
    )
    task_id = create.json()["id"]
    response = await auth_client.patch(f"/api/tasks/{task_id}", json={"status": "completed"})
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_update_task_conflict(auth_client: AsyncClient):
    await auth_client.post(
        "/api/tasks/",
        json={"title": "Blocker", "scheduled_date": "2026-04-04", "start_time": "14:00", "end_time": "16:00"},
    )
    create = await auth_client.post(
        "/api/tasks/",
        json={"title": "Mover", "scheduled_date": "2026-04-04", "start_time": "10:00", "end_time": "12:00"},
    )
    task_id = create.json()["id"]
    response = await auth_client.patch(f"/api/tasks/{task_id}", json={"start_time": "15:00", "end_time": "17:00"})
    assert response.status_code == 409