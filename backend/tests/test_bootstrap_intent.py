"""Slice 1 / Task 1.4: bootstrap-token intent + hostname + one-active guards.

Pins design D2:
- intent enforced at ISSUE (via the intent parameter) and re-checked at
  CONSUMPTION inside the transaction, BEFORE the consuming UPDATE — a
  rejected attempt never burns the token;
- hostnames are normalized (strip + lowercase) at both ends;
- at most one ACTIVE token per hostname (service guard + partial unique
  index with fail-safe migration skip);
- list endpoint supports ?active=true&limit= for the onboarding hook.
"""

from datetime import datetime, timedelta, timezone

from backend.app.services import enrollment as enrollment_service
from backend.tests.conftest import auth_headers
from backend.tests.test_bootstrap_enrollment import _admin, _issue


def _bootstrap_enroll(client, hostname, token):
    return client.post("/api/v1/agents/enroll", json={"hostname": hostname, "bootstrap_token": token})


def test_enroll_intent_rejects_existing_hostname(client, db_session):
    """intent=enroll on an existing hostname is rejected (409 HOSTNAME_TAKEN)."""
    admin = _admin(client, db_session)
    tok1 = _issue(client, admin, "exists-host").json()["token"]
    assert _bootstrap_enroll(client, "exists-host", tok1).status_code == 200

    tok2 = _issue(client, admin, "exists-host").json()["token"]
    resp = _bootstrap_enroll(client, "exists-host", tok2)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "HOSTNAME_TAKEN"


def test_enroll_intent_rejects_revoked_hostname(client, db_session):
    """A revoked host is still an existing host for the enroll intent."""
    admin = _admin(client, db_session)
    tok1 = _issue(client, admin, "gone-host").json()["token"]
    first = _bootstrap_enroll(client, "gone-host", tok1)
    assert first.status_code == 200
    host_id = first.json()["host_id"]

    # Revoke via the lifecycle endpoint.
    from backend.tests.test_operator_auth import _seed_operator

    from backend.app.core.db import SessionLocal
    from backend.app.services.host_lifecycle import revoke_host

    db = SessionLocal()
    try:
        revoke_host(db, host_id, "admin")
    finally:
        db.close()

    tok2 = _issue(client, admin, "gone-host").json()["token"]
    resp = _bootstrap_enroll(client, "gone-host", tok2)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "HOSTNAME_TAKEN"


def test_reenroll_intent_requires_existing_hostname(client, db_session):
    """intent=reenroll with no such host → 404 HOST_NOT_FOUND; token unburned."""
    from sqlalchemy import select
    from backend.app.core.security import generate_agent_token, hash_session_token, hash_token
    from backend.app.models import BootstrapToken, Host

    admin = _admin(client, db_session)
    tok = _issue(client, admin, "phantom-host", intent="reenroll").json()["token"]
    resp = _bootstrap_enroll(client, "phantom-host", tok)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "HOST_NOT_FOUND"

    # The token survives the rejection unburned.
    row = db_session.scalar(select(BootstrapToken).where(BootstrapToken.token_hash == hash_session_token(tok)))
    assert row.consumed_at is None

    # Once the host exists, the same token can now be consumed successfully.
    host = Host(hostname="phantom-host", agent_token_hash=hash_token(generate_agent_token()))
    db_session.add(host)
    db_session.commit()

    resp2 = _bootstrap_enroll(client, "phantom-host", tok)
    assert resp2.status_code == 200


def test_hostname_normalization_matches(client, db_session):
    """'Host-1' issued, 'host-1' consumed — same identity (normalized)."""
    admin = _admin(client, db_session)
    tok = _issue(client, admin, "Host-1").json()["token"]
    resp = _bootstrap_enroll(client, "host-1", tok)
    assert resp.status_code == 200, resp.text
    # The stored hostname is the normalized form.
    host_id = resp.json()["host_id"]
    from backend.app.core.db import SessionLocal
    from backend.app.models import Host

    db = SessionLocal()
    try:
        assert db.get(Host, host_id).hostname == "host-1"
    finally:
        db.close()


def test_mismatch_rejected_without_burning(client, db_session):
    """Wrong hostname → 401 MISMATCH; the token still works for the right one."""
    admin = _admin(client, db_session)
    tok = _issue(client, admin, "right-host").json()["token"]
    resp = _bootstrap_enroll(client, "wrong-host", tok)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "BOOTSTRAP_TOKEN_HOSTNAME_MISMATCH"
    assert _bootstrap_enroll(client, "right-host", tok).status_code == 200


def test_second_active_token_conflicts(client, db_session):
    """409 BOOTSTRAP_TOKEN_ACTIVE on a second active token; revoke frees the name."""
    admin = _admin(client, db_session)
    first = _issue(client, admin, "busy-host")
    assert first.status_code == 201
    second = _issue(client, admin, "busy-host")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "BOOTSTRAP_TOKEN_ACTIVE"

    # Revoke the first token (id from the list), then reissue succeeds.
    listing = client.get(
        "/api/v1/operators/bootstrap-tokens?active=true",
        headers={"Authorization": f"Bearer {admin}"},
    ).json()
    tok_id = listing["tokens"][0]["id"]
    del_resp = client.delete(
        f"/api/v1/operators/bootstrap-tokens/{tok_id}",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert del_resp.status_code in (200, 204)
    third = _issue(client, admin, "busy-host")
    assert third.status_code == 201


def test_expired_active_token_revoked_on_issue(client, db_session, monkeypatch):
    """An expired-but-unconsumed token no longer blocks a fresh issue."""
    from backend.app.core.config import get_settings
    from backend.app.models import BootstrapToken

    admin = _admin(client, db_session)
    first = _issue(client, admin, "stale-host").json()
    # Force-expire the first token row.
    db = db_session
    row = db.query(BootstrapToken).filter(BootstrapToken.hostname == "stale-host").one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    second = _issue(client, admin, "stale-host")
    assert second.status_code == 201, second.text


def test_list_active_filter_and_limit(client, db_session):
    """?active=true&limit= drives the onboarding hook."""
    admin = _admin(client, db_session)
    a = _issue(client, admin, "flt-host-a").json()["token"]
    b = _issue(client, admin, "flt-host-b").json()["token"]
    _bootstrap_enroll(client, "flt-host-a", a)  # consumed

    active = client.get(
        "/api/v1/operators/bootstrap-tokens?active=true",
        headers={"Authorization": f"Bearer {admin}"},
    ).json()
    assert {t["hostname"] for t in active["tokens"]} == {"flt-host-b"}

    limited = client.get(
        "/api/v1/operators/bootstrap-tokens?limit=1",
        headers={"Authorization": f"Bearer {admin}"},
    ).json()
    assert len(limited["tokens"]) == 1


def test_intent_recorded_on_row(client, db_session):
    """The issued row carries its intent (consumer reads it for the re-check)."""
    from backend.app.models import BootstrapToken

    admin = _admin(client, db_session)
    _issue(client, admin, "intent-host", intent="reenroll")
    row = db_session.query(BootstrapToken).filter(BootstrapToken.hostname == "intent-host").one()
    assert row.intent == "reenroll"
