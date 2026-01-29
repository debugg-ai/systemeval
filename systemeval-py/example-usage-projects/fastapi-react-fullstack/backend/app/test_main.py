import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "backend"


@pytest.mark.asyncio
async def test_list_users():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/users")
        assert resp.status_code == 200
        users = resp.json()
        assert isinstance(users, list)
        assert len(users) >= 2


@pytest.mark.asyncio
async def test_get_user():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/users/1")
        assert resp.status_code == 200
        user = resp.json()
        assert user["id"] == 1
        assert user["name"] == "Alice"


@pytest.mark.asyncio
async def test_get_user_not_found():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/users/999")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_user():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/users",
            json={"name": "Charlie", "email": "charlie@example.com"},
        )
        assert resp.status_code == 201
        user = resp.json()
        assert user["name"] == "Charlie"
        assert user["email"] == "charlie@example.com"
        assert "id" in user
