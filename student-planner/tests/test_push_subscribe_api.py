import pytest
from httpx import AsyncClient


SUBSCRIPTION_PAYLOAD = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/fake-token",
    "keys": {
        "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8p8REfWPU=",
        "auth": "tBHItJI5svbpC7-BnWW_IA==",
    },
}


@pytest.mark.asyncio
async def test_subscribe_push(auth_client: AsyncClient):
    response = await auth_client.post("/api/push/subscribe", json=SUBSCRIPTION_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["status"] == "subscribed"


@pytest.mark.asyncio
async def test_subscribe_then_get_vapid_key(auth_client: AsyncClient):
    response = await auth_client.get("/api/push/vapid-key")
    assert response.status_code == 200
    assert "public_key" in response.json()


@pytest.mark.asyncio
async def test_push_status_reflects_subscription_presence(auth_client: AsyncClient):
    response = await auth_client.get("/api/push/status")
    assert response.status_code == 200
    assert response.json()["subscribed"] is False
    assert "vapid_configured" in response.json()

    response = await auth_client.post("/api/push/subscribe", json=SUBSCRIPTION_PAYLOAD)
    assert response.status_code == 200

    response = await auth_client.get("/api/push/status")
    assert response.status_code == 200
    assert response.json()["subscribed"] is True


@pytest.mark.asyncio
async def test_unsubscribe_push(auth_client: AsyncClient):
    await auth_client.post("/api/push/subscribe", json=SUBSCRIPTION_PAYLOAD)
    response = await auth_client.delete("/api/push/subscribe")
    assert response.status_code == 200
    assert response.json()["status"] == "unsubscribed"


@pytest.mark.asyncio
async def test_subscribe_requires_auth(client: AsyncClient):
    response = await client.post("/api/push/subscribe", json=SUBSCRIPTION_PAYLOAD)
    assert response.status_code == 403
