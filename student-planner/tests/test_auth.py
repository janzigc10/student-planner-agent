import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    response = await client.post("/api/auth/register", json={"username": "alice", "password": "pass123"})
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "alice"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate(client: AsyncClient):
    await client.post("/api/auth/register", json={"username": "bob", "password": "pass123"})
    response = await client.post("/api/auth/register", json={"username": "bob", "password": "pass123"})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    await client.post("/api/auth/register", json={"username": "carol", "password": "pass123"})
    response = await client.post("/api/auth/login", json={"username": "carol", "password": "pass123"})
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/auth/register", json={"username": "dave", "password": "pass123"})
    response = await client.post("/api/auth/login", json={"username": "dave", "password": "wrong"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me(auth_client: AsyncClient):
    response = await auth_client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["username"] == "testuser"


@pytest.mark.asyncio
async def test_me_no_token(client: AsyncClient):
    response = await client.get("/api/auth/me")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_me_preferences(auth_client: AsyncClient):
    response = await auth_client.patch(
        "/api/auth/me",
        json={
            "current_semester_start": "2026-03-02",
            "preferences": {
                "earliest_study_time": "08:30",
                "latest_study_time": "22:30",
                "default_reminder_minutes": 30,
                "period_schedule": {
                    "1-2": {"start": "08:20", "end": "10:00"},
                },
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["current_semester_start"] == "2026-03-02"
    assert data["preferences"]["default_reminder_minutes"] == 30
    assert data["preferences"]["period_schedule"]["1-2"]["start"] == "08:20"
