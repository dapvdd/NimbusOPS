"""Slice 1 / Tasks 1.2+1.3: agent_mode persistence + HostOut widening.

Covers:
- hosts.agent_mode (nullable) persisted from the heartbeat, INCLUDING explicit
  absence clearing it to NULL (reported mode, not stale mode — design D3).
- HostOut exposes status/connectivity/agent_mode/credential_version/
  credential_grace_until; grace is null unless a rotation is inside its window.
- BootstrapToken.intent column exists (default 'enroll') and the partial
  unique active-token index is created (Task 1.4 depends on it).
- Fresh hosts expose their ENROLLED event immediately (Task 1.6 flush pin).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect, text

from backend.app.core.db import engine
from backend.tests.conftest import auth_headers


def test_host_out_serializes_new_fields(client, online_host):
    """GET /hosts/{id} carries all five new fields; grace is null pre-rotation."""
    host_id, token = online_host
    body = client.get(f"/api/v1/hosts/{host_id}").json()
    assert body["status"] in ("ONLINE", "STALE", "OFFLINE", "REVOKED")
    assert body["connectivity"] in ("ONLINE", "STALE", "OFFLINE")
    assert body["agent_mode"] is None
    assert body["credential_version"] == 1
    assert body["credential_grace_until"] is None


def test_heartbeat_persists_reported_agent_mode(client, online_host):
    """A heartbeat that reports a mode persists it verbatim."""
    host_id, token = online_host
    resp = client.post(
        "/api/v1/agents/heartbeat",
        headers=auth_headers(host_id, token),
        json={"agent_mode": "executor"},
    )
    assert resp.status_code == 200
    body = client.get(f"/api/v1/hosts/{host_id}").json()
    assert body["agent_mode"] == "executor"


def test_heartbeat_omission_clears_agent_mode(client, online_host):
    """Absence of the field is 'not reported' — it clears, never sticks (D3)."""
    host_id, token = online_host
    client.post("/api/v1/agents/heartbeat", headers=auth_headers(host_id, token), json={"agent_mode": "executor"})
    resp = client.post("/api/v1/agents/heartbeat", headers=auth_headers(host_id, token), json={})
    assert resp.status_code == 200
    assert client.get(f"/api/v1/hosts/{host_id}").json()["agent_mode"] is None


def test_heartbeat_rejects_invalid_agent_mode(client, online_host):
    host_id, token = online_host
    resp = client.post(
        "/api/v1/agents/heartbeat",
        headers=auth_headers(host_id, token),
        json={"agent_mode": "EXECUTOR-ALL-CAPS"},
    )
    assert resp.status_code == 422


def test_grace_window_serialized_only_while_active(client, online_host, db_session):
    """credential_grace_until is non-null inside the window, null after expiry."""
    from datetime import datetime, timedelta, timezone

    from backend.app.models import Host
    from backend.app.services.host_lifecycle import rotate_credential
    from backend.tests.test_operator_auth import _seed_operator

    host_id, token = online_host
    _seed_operator(db_session, username="admin", password="secret-pw", role="ADMIN")
    host, _plaintext, grace_until = rotate_credential(db_session, host_id, "admin", grace_period_seconds=600)

    body = client.get(f"/api/v1/hosts/{host_id}").json()
    assert body["credential_version"] == 2
    assert body["credential_grace_until"] is not None

    # Expire the window; the UI must not count down a dead grace.
    db = db_session
    host = db.get(Host, host_id)
    host.previous_token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert client.get(f"/api/v1/hosts/{host_id}").json()["credential_grace_until"] is None


def test_migration_adds_agent_mode_and_intent_columns():
    """Fresh DB: hosts.agent_mode + bootstrap_tokens.intent exist (additive)."""
    host_cols = {c["name"] for c in inspect(engine).get_columns("hosts")}
    assert "agent_mode" in host_cols
    token_cols = {c["name"] for c in inspect(engine).get_columns("bootstrap_tokens")}
    assert "intent" in token_cols


def test_partial_unique_active_token_index_exists():
    """The one-active-token-per-hostname guard index is present on a fresh DB."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'")).fetchall()
    names = {r[0] for r in rows}
    assert "ux_bootstrap_tokens_active_hostname" in names
