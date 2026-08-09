"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def client(tmp_path) -> TestClient:
    from app.main import create_app

    db_path = tmp_path / "test.db"
    app = create_app(db_url=f"sqlite:///{db_path}")
    return TestClient(app)


@pytest.fixture()
def auth_headers(client) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "username": "tester", "password": "password123"},
    )
    assert res.status_code in (200, 201), res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}