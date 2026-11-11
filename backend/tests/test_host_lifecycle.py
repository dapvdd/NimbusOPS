"""Task 5: host lifecycle — revocation, rotation with grace, operator re-enroll.

Covers PHASE3B_API_CONTRACT.md §4 (lifecycle endpoints) and threat-model T1
(credential compromise → rotate), plus:
- revoke → next agent call 401, tombstone retained (never deleted), telemetry
  history preserved, listed with enrollment_status REVOKED
- rotate → new token works immediately; old token works within grace; 401
  after grace expires
- re-enroll → ADMIN-only bootstrap issuance scoped to the existing hostname;
  un-revoke happens only when the agent consumes that token
- all three ADMIN-only (VIEWER → 403)
- audit events with actor
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.app.core.db import SessionLocal
from backend.app.models import Host, HostEvent
from backend.tests.test_operator_auth import _seed_operator


def _login(client, username="admin", password="secret-pw") -> str:
    _seed_operator(_db(), username=username, password=password)
    resp = client.post("/api/v1/operators/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["session_token"]


def _db():
    from backend.app.core.db import SessionLocal as SL

    return SL()


def _revoke(client, admin, host_id):
    return client.delete(f"/api/v1/hosts/{host_id}", headers={"Authorization": f"Bearer {admin}"})


def _rotate(client, admin, host_id, grace=300):
    return client.post(
        f"/api/v1/hosts/{host_id}/rotate-credential",
        headers={"Authorization": f"Bearer {admin}"},
        json={"grace_period_seconds": grace},
    )


def _reenroll_bootstrap(client, admin, host_id):
    return client.post(
        f"/api/v1/hosts/{host_id}/re-enroll",
        headers={"Authorization": f"Bearer {admin}"},
        json={"new_bootstrap_token": True},
    )


def _hb(client, host_id, token):
    return client.post(
        "/api/v1/agents/heartbeat",
        headers={"X-Host-Id": host_id, "Authorization": f"Bearer {token}"},
        json={},
    )


# ------------------------------------------------------------------ revoke


def test_revoke_blocks_agent_and_keeps_tombstone(client, online_host):
    admin = _login(client)
    host_id, token = online_host
    # Leave telemetry evidence.
    client.post(
        "/api/v1/agents/telemetry",
        headers={"X-Host-Id": host_id, "Authorization": f"Bearer {token}"},
        json={
            "recorded_at": "2026-11-10T12:00:00Z",
            "cpu_percent": 10.0,
            "memory_used_bytes": 1,
            "memory_total_bytes": 2,
            "disk_used_bytes": 1,
            "disk_total_bytes": 2,
        },
    )

    resp = _revoke(client, admin, host_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["enrollment_status"] == "REVOKED"
    assert body["revoked_at"] is not None

    # Agent blocked on next heartbeat.
    assert _hb(client, host_id, token).status_code == 401

    # Tombstone retained with telemetry history; listed as REVOKED.
    detail = client.get(f"/api/v1/hosts/{host_id}")
    assert detail.status_code == 200
    assert detail.json()["is_revoked"] is True
    assert detail.json()["enrollment_status"] == "REVOKED"
    listing = client.get("/api/v1/hosts").json()
    assert any(h["id"] == host_id for h in listing["hosts"])
    metrics = client.get(f"/api/v1/hosts/{host_id}/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["count"] >= 1

    # Tombstone never deleted: row still present in DB.
    db = SessionLocal()
    try:
        assert db.get(Host, host_id) is not None
    finally:
        db.close()

    # Idempotent second revoke.
    assert _revoke(client, admin, host_id).status_code == 200


def test_revoke_requires_admin(client, online_host):
    _seed_operator(_db(), username="viewer", role="VIEWER")
    resp = client.post("/api/v1/operators/login", json={"username": "viewer", "password": "secret-pw"})
    viewer = resp.json()["session_token"]
    host_id, _tok = online_host
    r = _revoke(client, viewer, host_id)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "OPERATOR_FORBIDDEN"


def test_revoke_requires_auth(client, online_host):
    host_id, _tok = online_host
    assert client.delete(f"/api/v1/hosts/{host_id}").status_code == 401


# ------------------------------------------------------------------ rotate


def test_rotate_new_token_immediate_old_within_grace(client, online_host):
    admin = _login(client)
    host_id, old_token = online_host
    resp = _rotate(client, admin, host_id, grace=300)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["host_id"] == host_id
    assert body["new_agent_token"] != old_token
    assert body["old_token_expires_at"]

    # New token works immediately.
    assert _hb(client, host_id, body["new_agent_token"]).status_code == 200
    # Old token works within the grace window.
    assert _hb(client, host_id, old_token).status_code == 200


def test_rotate_old_token_rejected_after_grace(client, online_host):
    admin = _login(client)
    host_id, old_token = online_host
    resp = _rotate(client, admin, host_id, grace=300)
    new_token = resp.json()["new_agent_token"]

    # Force the grace window to be over.
    db = SessionLocal()
    try:
        host = db.get(Host, host_id)
        host.previous_token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()

    assert _hb(client, host_id, old_token).status_code == 401
    assert _hb(client, host_id, new_token).status_code == 200


def test_rotate_requires_admin_and_auth(client, online_host):
    _seed_operator(_db(), username="viewer", role="VIEWER")
    viewer = client.post("/api/v1/operators/login", json={"username": "viewer", "password": "secret-pw"}).json()["session_token"]
    host_id, _tok = online_host
    assert _rotate(client, viewer, host_id).status_code == 403
    assert _rotate(client, "", host_id).status_code == 401


# ---------------------------------------------------------------- re-enroll


def test_reenroll_issues_scoped_bootstrap_restores_host(client, online_host):
    admin = _login(client)
    host_id, old_token = online_host
    assert _revoke(client, admin, host_id).status_code == 200

    resp = _reenroll_bootstrap(client, admin, host_id)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["bootstrap_token"]
    assert body["expires_at"]

    # Host still revoked until the agent consumes the bootstrap token.
    detail = client.get(f"/api/v1/hosts/{host_id}").json()
    assert detail["enrollment_status"] == "REVOKED"
    assert _hb(client, host_id, old_token).status_code == 401

    # Agent completes enrollment with the bootstrap token → restored.
    enroll = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "deploy-host", "bootstrap_token": body["bootstrap_token"]},
    )
    assert enroll.status_code == 200
    assert enroll.json()["host_id"] == host_id  # same host identity

    detail = client.get(f"/api/v1/hosts/{host_id}").json()
    assert detail["enrollment_status"] == "ENROLLED"
    assert detail["is_revoked"] is False
    # New credential works; old stays dead.
    assert _hb(client, host_id, enroll.json()["agent_token"]).status_code == 200
    assert _hb(client, host_id, old_token).status_code == 401


def test_reenroll_requires_admin(client, online_host):
    _seed_operator(_db(), username="viewer", role="VIEWER")
    viewer = client.post("/api/v1/operators/login", json={"username": "viewer", "password": "secret-pw"}).json()["session_token"]
    host_id, _tok = online_host
    resp = _reenroll_bootstrap(client, viewer, host_id)
    assert resp.status_code == 403


def test_lifecycle_writes_audit_events_with_actor(client, online_host):
    admin = _login(client)
    host_id, _tok = online_host
    # Rotate while healthy, then revoke (rotate on a revoked host is 409).
    _rotate(client, admin, host_id)
    _revoke(client, admin, host_id)
    db = SessionLocal()
    try:
        events = {
            (e.event, e.actor)
            for e in db.scalars(select(HostEvent).where(HostEvent.host_id == host_id)).all()
        }
        assert ("HOST_REVOKED", "admin") in events
        assert ("CREDENTIAL_ROTATED", "admin") in events
    finally:
        db.close()
