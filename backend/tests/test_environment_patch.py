"""S4-3 Phase B: operator PATCH /api/v1/hosts/{id} environment.

Verifies:
- ADMIN → 200, host environment updated, ENVIRONMENT_CHANGED event written.
- VIEWER → 403.
- Invalid value → 422.
- The environment field is readable on GET /hosts/{id}.

RED (no implementation yet): these tests are written BEFORE the code change.
Expected outcome at RED: admin case returns 422 (HostPatchRequest rejects
environment field), viewer case returns 422 or 403 (endpoint may fail before
auth check if environment is unknown to the schema), invalid value may return
422 or 500.
"""

from __future__ import annotations

from sqlalchemy import select

from backend.app.core.db import SessionLocal
from backend.app.models import HostEvent
from backend.tests.test_operator_auth import _seed_operator


def _db():
    from backend.app.core.db import SessionLocal as SL

    return SL()


def _login(client, username="admin", password="secret-pw"):
    """Login as ADMIN (default) — mirrors test_host_lifecycle helper."""
    _seed_operator(_db(), username=username, password=password)
    resp = client.post("/api/v1/operators/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["session_token"]


def _login_viewer(client):
    """Login as VIEWER."""
    _seed_operator(_db(), username="viewer", role="VIEWER")
    resp = client.post("/api/v1/operators/login", json={"username": "viewer", "password": "secret-pw"})
    assert resp.status_code == 200, resp.text
    return resp.json()["session_token"]


def _patch_environment(client, token: str, host_id: str, environment: str):
    return client.patch(
        f"/api/v1/hosts/{host_id}",
        json={"environment": environment},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_patch_environment_admin_updates_and_audits(client, online_host):
    """ADMIN PATCH with valid environment value → 200, DB updated, event appended."""
    admin = _login(client)
    host_id, _token = online_host

    resp = _patch_environment(client, admin, host_id, "PUBLIC-CLOUD")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body.get("environment") == "PUBLIC-CLOUD"

    # DB row updated.
    db = SessionLocal()
    try:
        from backend.app.models import Host

        host = db.get(Host, host_id)
        assert host.environment == "PUBLIC-CLOUD"
    finally:
        db.close()

    # ENVIRONMENT_SET audit event written with actor (plan Phase B naming).
    db = SessionLocal()
    try:
        events = db.scalars(
            select(HostEvent)
            .where(HostEvent.host_id == host_id)
            .where(HostEvent.event == "ENVIRONMENT_SET")
        ).all()
        assert len(events) == 1, f"expected 1 ENVIRONMENT_SET event, found {len(events)}"
        assert events[0].actor == "admin"
    finally:
        db.close()


def test_patch_environment_viewer_forbidden(client, online_host):
    """VIEWER PATCH attempt → 403 OPERATOR_FORBIDDEN."""
    viewer = _login_viewer(client)
    host_id, _tok = online_host

    r = _patch_environment(client, viewer, host_id, "PUBLIC-CLOUD")
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"


def test_patch_environment_invalid_value_rejected(client, online_host):
    """Invalid environment value → 422 with FastAPI validation detail."""
    admin = _login(client)
    host_id, _tok = online_host

    r = _patch_environment(client, admin, host_id, "MARS")
    assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"
    body = r.json()
    # FastAPI validation errors carry {"detail": [...]} — confirm it's a real
    # validation rejection, not an auth or unrelated failure.
    assert "detail" in body, f"expected FastAPI 422 detail payload, got: {body}"


def test_patch_environment_unauthenticated_rejected(client, online_host):
    """No auth → 401."""
    host_id, _tok = online_host
    r = client.patch(
        f"/api/v1/hosts/{host_id}",
        json={"environment": "PUBLIC-CLOUD"},
    )
    assert r.status_code == 401


def test_patch_environment_private_roundtrip(client, online_host):
    """PUBLIC-CLOUD → PRIVATE roundtrip: both directions work."""
    admin = _login(client)
    host_id, _tok = online_host

    # Set PUBLIC-CLOUD.
    r = _patch_environment(client, admin, host_id, "PUBLIC-CLOUD")
    assert r.status_code == 200

    # Set back to PRIVATE.
    r = _patch_environment(client, admin, host_id, "PRIVATE")
    assert r.status_code == 200
    assert r.json().get("environment") == "PRIVATE"

    db = SessionLocal()
    try:
        from backend.app.models import Host

        host = db.get(Host, host_id)
        assert host.environment == "PRIVATE"
    finally:
        db.close()
