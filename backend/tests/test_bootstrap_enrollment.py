"""Phase 3B bootstrap-token enrollment tests (Task 3).

Covers PHASE3B_API_CONTRACT.md §3 (issue/list/revoke bootstrap tokens) and
§5.1 (secure enroll), plus threat-model items T2 (token replay), T3 (hostname
scope), T5 (silent un-revoke removal).

Legacy path (`enrollment_token`) still works during the Phase 3B transition
(decision O5), except the silent un-revoke, which is removed per plan.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.app.core.db import SessionLocal
from backend.app.core.security import generate_agent_token, hash_session_token
from backend.app.models import BootstrapToken, Host
from backend.tests.test_operator_auth import _seed_operator


def _issue(client, admin_token: str, hostname: str, expires_in: int | None = None):
    payload = {"hostname": hostname}
    if expires_in is not None:
        payload["expires_in_seconds"] = expires_in
    return client.post(
        "/api/v1/operators/bootstrap-tokens",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=payload,
    )


def _admin(client, db_session):
    _seed_operator(db_session)
    resp = client.post("/api/v1/operators/login", json={"username": "admin", "password": "secret-pw"})
    return resp.json()["session_token"]


def _enroll(client, hostname: str, bootstrap_token: str):
    return client.post(
        "/api/v1/agents/enroll",
        json={"hostname": hostname, "bootstrap_token": bootstrap_token},
    )


# --------------------------------------------------------------- §3.1 issue

def test_issue_bootstrap_token_returns_plaintext_once(client, db_session):
    admin = _admin(client, db_session)
    resp = _issue(client, admin, "new-host")
    assert resp.status_code == 201
    body = resp.json()
    assert body["hostname"] == "new-host"
    assert len(body["token"]) >= 32
    assert body["expires_at"]
    # Hash stored, never plaintext.
    db = SessionLocal()
    try:
        row = db.scalar(select(BootstrapToken).where(BootstrapToken.id == body["id"]))
        assert row is not None
        assert row.token_hash != body["token"]
        assert len(row.token_hash) == 64
        assert row.consumed_at is None
    finally:
        db.close()


def test_issue_requires_admin_role(client, db_session):
    _seed_operator(db_session, username="viewer", role="VIEWER")
    resp = client.post(
        "/api/v1/operators/login",
        json={"username": "viewer", "password": "secret-pw"},
    )
    token = resp.json()["session_token"]
    resp = _issue(client, token, "h")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "OPERATOR_FORBIDDEN"


def test_issue_requires_auth(client):
    resp = _issue(client, "", "h")
    assert resp.status_code == 401


def test_issue_rejects_unknown_expiry_cap(client, db_session):
    admin = _admin(client, db_session)
    resp = _issue(client, admin, "h", expires_in=3601)
    assert resp.status_code == 422


# --------------------------------------------------------------- §5.1 enroll

def test_enroll_with_valid_bootstrap_creates_host_and_consumes(client, db_session):
    admin = _admin(client, db_session)
    tok = _issue(client, admin, "boot-host").json()["token"]
    resp = _enroll(client, "boot-host", tok)
    assert resp.status_code == 200
    body = resp.json()
    assert body["host_id"]
    assert len(body["agent_token"]) >= 32
    db = SessionLocal()
    try:
        row = db.scalar(select(BootstrapToken).where(BootstrapToken.hostname == "boot-host"))
        assert row is not None
        assert row.consumed_at is not None
        assert row.consumed_by == body["host_id"]
        host = db.scalar(select(Host).where(Host.hostname == "boot-host"))
        assert host.enrollment_status == "ENROLLED"
        assert host.docker_enabled == 0
    finally:
        db.close()


def test_enroll_replay_same_token_409(client, db_session):
    admin = _admin(client, db_session)
    tok = _issue(client, admin, "replay-host").json()["token"]
    first = _enroll(client, "replay-host", tok)
    assert first.status_code == 200
    replay = _enroll(client, "replay-host", tok)
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "BOOTSTRAP_TOKEN_CONSUMED"


def test_enroll_expired_token_410(client, db_session):
    admin = _admin(client, db_session)
    tok = _issue(client, admin, "exp-host").json()["token"]
    # Force-expire.
    db = SessionLocal()
    try:
        row = db.scalar(select(BootstrapToken).where(BootstrapToken.hostname == "exp-host"))
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()
    resp = _enroll(client, "exp-host", tok)
    assert resp.status_code == 410
    assert resp.json()["error"]["code"] == "BOOTSTRAP_TOKEN_EXPIRED"


def test_enroll_revoked_token_401(client, db_session):
    admin = _admin(client, db_session)
    tok = _issue(client, admin, "rev-host").json()["token"]
    listed = client.get(
        "/api/v1/operators/bootstrap-tokens",
        headers={"Authorization": f"Bearer {admin}"},
    ).json()
    token_id = listed["tokens"][0]["id"]
    resp = client.delete(
        f"/api/v1/operators/bootstrap-tokens/{token_id}",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert resp.status_code == 200
    resp = _enroll(client, "rev-host", tok)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "BOOTSTRAP_TOKEN_INVALID"


def test_enroll_wrong_hostname_scope_401(client, db_session):
    admin = _admin(client, db_session)
    tok = _issue(client, admin, "right-host").json()["token"]
    resp = _enroll(client, "other-host", tok)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "BOOTSTRAP_TOKEN_INVALID"


def test_enroll_unknown_token_401(client):
    resp = _enroll(client, "ghost-host", generate_agent_token())
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "BOOTSTRAP_TOKEN_INVALID"


# ---------------------------------------------------------- legacy path (O5)

def test_legacy_enrollment_token_still_works(client, enroll_token):
    resp = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "legacy-host", "enrollment_token": enroll_token},
    )
    assert resp.status_code == 200


# ----------------------------------------------- removed silent un-revoke (T5)

def test_revoked_host_reenroll_requires_operator_bootstrap(client, db_session, enroll_token):
    """Old silent un-revoke is removed: legacy token cannot resurrect a REVOKED host."""
    # Enroll via legacy, then revoke directly at service level.
    r1 = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "gone-host", "enrollment_token": enroll_token},
    ).json()
    db = SessionLocal()
    try:
        host = db.scalar(select(Host).where(Host.hostname == "gone-host"))
        host.is_revoked = True
        host.revoked_at = datetime.now(timezone.utc)
        host.enrollment_status = "REVOKED"
        db.commit()
        host_id = host.id
    finally:
        db.close()

    # Legacy re-enroll with the same static token must now FAIL (hostname taken).
    resp = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "gone-host", "enrollment_token": enroll_token},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "HOSTNAME_TAKEN"

    # Even a *fresh* legacy path cannot touch it; only a bootstrap token for
    # this hostname re-enrolls (full flow tested in Task 5's re-enroll tests).
    admin = _admin(client, db_session)
    tok = _issue(client, admin, "gone-host").json()["token"]
    resp = _enroll(client, "gone-host", tok)
    assert resp.status_code == 200
    body = resp.json()
    assert body["host_id"] == host_id  # same host identity, tombstone restored
    db = SessionLocal()
    try:
        host = db.get(Host, host_id)
        assert host.is_revoked == 0
        assert host.enrollment_status == "ENROLLED"
    finally:
        db.close()


# ------------------------------------------------------------- concurrency

def test_concurrent_identical_enrollments_single_host(client, db_session):
    """Two agents presenting the same valid bootstrap token: exactly one host row."""
    admin = _admin(client, db_session)
    tok = _issue(client, admin, "race-host").json()["token"]

    import threading

    results: list = []

    def hit():
        c = client  # TestClient is thread-safe enough for a single post each
        results.append(_enroll(c, "race-host", tok).status_code)

    threads = [threading.Thread(target=hit) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == [200, 409]
    db = SessionLocal()
    try:
        hosts = db.scalars(select(Host).where(Host.hostname == "race-host")).all()
        assert len(hosts) == 1
    finally:
        db.close()


# ------------------------------------------------------------- §3.2/§3.3

def test_list_bootstrap_tokens_no_material(client, db_session):
    admin = _admin(client, db_session)
    _issue(client, admin, "list-host")
    listed = client.get(
        "/api/v1/operators/bootstrap-tokens",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["count"] >= 1
    entry = body["tokens"][0]
    for field in ("id", "hostname", "created_at", "expires_at", "consumed_at", "consumed_by_host_id", "revoked_at"):
        assert field in entry
    assert "token" not in entry
    assert "token_hash" not in entry


def test_revoke_unconsumed_token_then_use_fails(client, db_session):
    admin = _admin(client, db_session)
    tok = _issue(client, admin, "kill-host").json()["token"]
    listed = client.get(
        "/api/v1/operators/bootstrap-tokens",
        headers={"Authorization": f"Bearer {admin}"},
    ).json()
    token_id = listed["tokens"][0]["id"]
    rev = client.delete(
        f"/api/v1/operators/bootstrap-tokens/{token_id}",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert rev.status_code == 200
    assert rev.json()["revoked_at"] is not None
    # Idempotent second revoke.
    rev2 = client.delete(
        f"/api/v1/operators/bootstrap-tokens/{token_id}",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert rev2.status_code == 200
    assert _enroll(client, "kill-host", tok).status_code == 401


def test_revoke_consumed_token_conflict(client, db_session):
    admin = _admin(client, db_session)
    tok = _issue(client, admin, "used-host").json()["token"]
    assert _enroll(client, "used-host", tok).status_code == 200
    listed = client.get(
        "/api/v1/operators/bootstrap-tokens",
        headers={"Authorization": f"Bearer {admin}"},
    ).json()
    token_id = [t for t in listed["tokens"] if t["hostname"] == "used-host"][0]["id"]
    resp = client.delete(
        f"/api/v1/operators/bootstrap-tokens/{token_id}",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "BOOTSTRAP_TOKEN_CONSUMED"
