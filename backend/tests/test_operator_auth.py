"""Operator authentication tests: login, session lifecycle, RBAC guard.

Covers PHASE3B_API_CONTRACT.md §2 and threat-model I1 (no operator auth):
- login happy path issues a bearer session token (hashed at rest)
- wrong password → 401
- unknown operator → 401
- expired session → 401
- logout invalidates; logout is idempotent
- require_operator dependency rejects missing/invalid tokens
- VIEWER role cannot reach ADMIN-only endpoints (403 OPERATOR_FORBIDDEN)
"""

from datetime import datetime, timedelta, timezone

from backend.tests.conftest import auth_headers  # noqa: F401  (re-exported helper pattern)


def _login(client, username="admin", password="secret-pw"):
    return client.post("/api/v1/operators/login", json={"username": username, "password": password})


def _seed_operator(db_session, username="admin", password="secret-pw", role="ADMIN"):
    """Seed an operator directly (first operator is created out-of-band by script)."""
    from backend.app.core.security import hash_operator_password
    from backend.app.models import Operator

    op = Operator(username=username, password_hash=hash_operator_password(password), role=role)
    db_session.add(op)
    db_session.commit()
    return op


def test_login_success_returns_bearer_token(client, db_session):
    _seed_operator(db_session)
    resp = _login(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_token"]
    assert len(body["session_token"]) >= 32
    assert body["operator_id"]
    assert body["role"] == "ADMIN"
    assert body["expires_at"]


def test_login_wrong_password_401(client, db_session):
    _seed_operator(db_session)
    resp = _login(client, password="wrong")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"
    # Message must not leak which part was wrong in a way that helps enumeration.
    assert "password" not in resp.json()["error"]["message"].lower()


def test_login_unknown_operator_401(client, db_session):
    resp = _login(client, username="nobody")
    assert resp.status_code == 401


def test_expired_session_rejected(client, db_session):
    _seed_operator(db_session)
    body = _login(client).json()
    token = body["session_token"]
    # Force-expire the session row.
    from backend.app.core.db import SessionLocal
    from backend.app.models import OperatorSession

    db = SessionLocal()
    try:
        sess = db.query(OperatorSession).filter(OperatorSession.operator_id == body["operator_id"]).one()
        sess.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()
    resp = client.get("/api/v1/operators/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_logout_invalidates_session_idempotent(client, db_session):
    _seed_operator(db_session)
    token = _login(client).json()["session_token"]
    h = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/operators/logout", headers=h).status_code == 200
    # Second logout: idempotent 200 (session already gone).
    assert client.post("/api/v1/operators/logout", headers=h).status_code == 200
    # Token no longer works.
    assert client.get("/api/v1/operators/me", headers=h).status_code == 401


def test_me_returns_operator_identity(client, db_session):
    _seed_operator(db_session)
    token = _login(client).json()["session_token"]
    resp = client.get("/api/v1/operators/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "admin"
    assert body["role"] == "ADMIN"


def test_me_requires_token(client):
    assert client.get("/api/v1/operators/me").status_code == 401


def test_viewer_cannot_call_admin_endpoints(client, db_session):
    """RBAC: require_operator(role="ADMIN") rejects VIEWER with 403 OPERATOR_FORBIDDEN.

    Probes the dependency directly on a temporary ADMIN-only route (the real
    ADMIN endpoints arrive with Tasks 3/5; this test pins the Task 2 product,
    not a Task 3 route).
    """
    _seed_operator(db_session, username="viewer", role="VIEWER")
    token = _login(client, username="viewer").json()["session_token"]

    from fastapi import Depends

    from backend.app.api.operators import require_operator
    from backend.app.main import app

    @app.post("/api/v1/operators/_rbac-probe", include_in_schema=False)
    async def _probe(op: object = Depends(require_operator(role="ADMIN"))):
        return {"ok": True}

    try:
        resp = client.post("/api/v1/operators/_rbac-probe", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "OPERATOR_FORBIDDEN"
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/api/v1/operators/_rbac-probe"]


def test_session_token_hashed_at_rest(client, db_session):
    _seed_operator(db_session)
    token = _login(client).json()["session_token"]
    from sqlalchemy import select

    from backend.app.core.db import SessionLocal
    from backend.app.models import OperatorSession

    db = SessionLocal()
    try:
        rows = db.scalars(select(OperatorSession)).all()
        assert rows, "session row should exist"
        for r in rows:
            assert r.token_hash != token, "plaintext token must never be stored"
            assert len(r.token_hash) == 64  # sha256 hex
    finally:
        db.close()
