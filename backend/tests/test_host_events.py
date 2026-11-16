"""Slice 1 / Task 1.5: host events history endpoint.

Spec: GET /api/v1/hosts/{id}/events?limit=
- Order: newest first (order_by(HostEvent.at.desc()))
- Limit: optional limit parameter (default 50, capped at 200)
- Auth: requires operator session (VIEWER allowed, 401 if unauthenticated)
- Content: id, host_id, event, actor, detail, at / created_at; no secret token material
"""

from datetime import datetime, timezone

from backend.app.core.db import SessionLocal
from backend.app.models import HostEvent
from backend.app.services.host_lifecycle import revoke_host, rotate_credential
from backend.tests.test_bootstrap_enrollment import _admin, _issue
from backend.tests.test_operator_auth import _seed_operator


def _bootstrap_enroll(client, hostname, token):
    return client.post("/api/v1/agents/enroll", json={"hostname": hostname, "bootstrap_token": token})


def test_events_newest_first_and_limit(client, db_session):
    """Enroll -> rotate -> revoke generates events; GET returns them newest-first and respects limit."""
    admin = _admin(client, db_session)
    tok = _issue(client, admin, "audit-host").json()["token"]
    res = _bootstrap_enroll(client, "audit-host", tok)
    assert res.status_code == 200
    host_id = res.json()["host_id"]

    # Trigger lifecycle actions that record host events
    rotate_credential(db_session, host_id, "admin", grace_period_seconds=60)
    revoke_host(db_session, host_id, "admin")

    resp = client.get(
        f"/api/v1/hosts/{host_id}/events",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "events" in data
    assert data["count"] >= 2
    events = data["events"]
    # Verify newest first
    for i in range(len(events) - 1):
        t1 = datetime.fromisoformat(events[i]["at"])
        t2 = datetime.fromisoformat(events[i + 1]["at"])
        assert t1 >= t2

    # Verify limit
    resp_lim = client.get(
        f"/api/v1/hosts/{host_id}/events?limit=1",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert resp_lim.status_code == 200
    assert len(resp_lim.json()["events"]) == 1


def test_events_readable_by_viewer_and_requires_auth(client, db_session):
    """VIEWER role can read events; anonymous access is 401 Unauthorized."""
    _seed_operator(db_session, username="viewer_user", role="VIEWER")
    viewer_resp = client.post("/api/v1/operators/login", json={"username": "viewer_user", "password": "secret-pw"})
    assert viewer_resp.status_code == 200
    viewer_token = viewer_resp.json()["session_token"]

    admin = _admin(client, db_session)
    tok = _issue(client, admin, "viewer-audit-host").json()["token"]
    res = _bootstrap_enroll(client, "viewer-audit-host", tok)
    host_id = res.json()["host_id"]

    # Anonymous -> 401
    from starlette.testclient import TestClient
    from backend.app.main import app
    unauth_client = TestClient(app)
    unauth_resp = unauth_client.get(f"/api/v1/hosts/{host_id}/events")
    assert unauth_resp.status_code == 401

    # VIEWER -> 200
    v_resp = client.get(
        f"/api/v1/hosts/{host_id}/events",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert v_resp.status_code == 200


def test_events_contain_no_token_material(client, db_session):
    """Event details must never include plaintext agent tokens or session tokens."""
    admin = _admin(client, db_session)
    tok = _issue(client, admin, "secret-audit-host").json()["token"]
    res = _bootstrap_enroll(client, "secret-audit-host", tok)
    host_id = res.json()["host_id"]
    agent_token = res.json()["agent_token"]

    _host, new_token, _grace = rotate_credential(db_session, host_id, "admin", grace_period_seconds=60)

    resp = client.get(
        f"/api/v1/hosts/{host_id}/events",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for ev in data["events"]:
        detail = ev.get("detail") or ""
        assert tok not in detail
        assert agent_token not in detail
        assert new_token not in detail


def test_fresh_host_enrolled_event_immediately_visible(client, db_session):
    """A fresh host's history must include its ENROLLED event immediately."""
    admin = _admin(client, db_session)
    tok = _issue(client, admin, "fresh-event-host").json()["token"]
    res = _bootstrap_enroll(client, "fresh-event-host", tok)
    assert res.status_code == 200
    host_id = res.json()["host_id"]

    resp = client.get(
        f"/api/v1/hosts/{host_id}/events",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert resp.status_code == 200
    events = resp.json()["events"]
    assert any(e["event"] == "ENROLLED" for e in events)
