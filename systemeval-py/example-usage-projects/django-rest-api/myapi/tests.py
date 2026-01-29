from django.test import Client


def test_health_endpoint():
    client = Client()
    response = client.get("/api/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_items_endpoint():
    client = Client()
    response = client.get("/api/items/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_items_count():
    client = Client()
    response = client.get("/api/items/")
    data = response.json()
    assert len(data) == 2
