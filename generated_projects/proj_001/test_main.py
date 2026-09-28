"""
test_main.py - Pytest integration test suite for proj_001
"""
import os
import pytest
from fastapi.testclient import TestClient

from main import app
from models import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    yield


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["project"] == "proj_001"


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_create_and_get_item():
    new_item = {
        "title": "Software Engineering Internship",
        "category": "engineering",
        "description": "Full stack internship opportunity",
        "status": "active"
    }
    post_res = client.post("/api/items", json=new_item)
    assert post_res.status_code == 201
    created = post_res.json()
    assert created["title"] == new_item["title"]
    item_id = created["id"]

    get_res = client.get(f"/api/items/{item_id}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == new_item["title"]


def test_list_items():
    res = client.get("/api/items")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
