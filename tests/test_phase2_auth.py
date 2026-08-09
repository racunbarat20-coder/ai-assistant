"""Phase 2 tests: auth (register/login/me) & conversation CRUD."""

from __future__ import annotations


def test_register_returns_token_and_user(client):
    res = client.post(
        "/api/v1/auth/register",
        json={"email": "a@b.com", "username": "alice", "password": "secret123"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["access_token"]
    assert body["user"]["email"] == "a@b.com"
    assert "password" not in body["user"]


def test_register_rejects_duplicate(client):
    payload = {"email": "dup@b.com", "username": "bob", "password": "secret123"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 409


def test_register_rejects_weak_password(client):
    res = client.post(
        "/api/v1/auth/register", json={"email": "x@b.com", "username": "x", "password": "short"}
    )
    assert res.status_code == 422


def test_login_success_and_failure(client):
    client.post(
        "/api/v1/auth/register", json={"email": "l@b.com", "username": "login", "password": "secret123"}
    )
    ok = client.post("/api/v1/auth/login", json={"email": "l@b.com", "password": "secret123"})
    assert ok.status_code == 200
    bad = client.post("/api/v1/auth/login", json={"email": "l@b.com", "password": "wrong123"})
    assert bad.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_with_token(client, auth_headers):
    res = client.get("/api/v1/auth/me", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["username"] == "tester"


def test_password_hash_roundtrip():
    from app.core.security import hash_password, verify_password

    h = hash_password("secret123")
    assert h.startswith("pbkdf2_sha256$")
    assert verify_password("secret123", h)
    assert not verify_password("wrong123", h)


def test_conversation_crud(client, auth_headers):
    # create
    res = client.post("/api/v1/conversations", json={"title": "Tanya data"}, headers=auth_headers)
    assert res.status_code == 201
    conv_id = res.json()["id"]
    assert res.json()["messages"] == []

    # list
    listed = client.get("/api/v1/conversations", headers=auth_headers)
    assert listed.status_code == 200
    ids = [c["id"] for c in listed.json()]
    assert conv_id in ids

    # get detail
    detail = client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers)
    assert detail.status_code == 200

    # delete
    assert client.delete(f"/api/v1/conversations/{conv_id}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers).status_code == 404


def test_conversation_isolated_between_users(client):
    first = client.post(
        "/api/v1/auth/register", json={"email": "u1@b.com", "username": "u1", "password": "secret123"}
    ).json()["access_token"]
    second = client.post(
        "/api/v1/auth/register", json={"email": "u2@b.com", "username": "u2", "password": "secret123"}
    ).json()["access_token"]

    conv_id = client.post(
        "/api/v1/conversations", json={}, headers={"Authorization": f"Bearer {first}"}
    ).json()["id"]

    # user2 cannot read user1's conversation
    res = client.get(
        f"/api/v1/conversations/{conv_id}", headers={"Authorization": f"Bearer {second}"}
    )
    assert res.status_code == 404
    res2 = client.delete(
        f"/api/v1/conversations/{conv_id}", headers={"Authorization": f"Bearer {second}"}
    )
    assert res2.status_code == 404


def test_audit_logs_written(client, auth_headers):
    from app.db.base import session_scope
    from app.db.models import AuditLog

    client.post("/api/v1/conversations", json={}, headers=auth_headers)
    with session_scope() as db:
        actions = {r[0] for r in db.query(AuditLog.action).all()}
    assert {"auth.register", "conversation.create"} <= actions