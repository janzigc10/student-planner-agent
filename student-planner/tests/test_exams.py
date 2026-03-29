import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_exam(auth_client: AsyncClient):
    response = await auth_client.post(
        "/api/exams/",
        json={"type": "exam", "date": "2026-04-05", "description": "高等数学期中考试"},
    )
    assert response.status_code == 201
    assert response.json()["date"] == "2026-04-05"


@pytest.mark.asyncio
async def test_list_exams(auth_client: AsyncClient):
    await auth_client.post("/api/exams/", json={"date": "2026-04-10", "type": "assignment"})
    response = await auth_client.get("/api/exams/")
    assert response.status_code == 200
    assert len(response.json()) >= 1


@pytest.mark.asyncio
async def test_delete_exam(auth_client: AsyncClient):
    create = await auth_client.post("/api/exams/", json={"date": "2026-05-01", "type": "exam"})
    exam_id = create.json()["id"]
    response = await auth_client.delete(f"/api/exams/{exam_id}")
    assert response.status_code == 204