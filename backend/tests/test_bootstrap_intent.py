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

import pytest

from backend.app.services import enrollment as enrollment_service
from backend.app.models import Operator
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


def test_concurrent_issue_second_gets_409_before_insert(client, db_session):
    """Pre-insert active-token guard: the second issuance fails closed with
    409 BOOTSTRAP_TOKEN_ACTIVE even when both run before either first
    issuance commits (the race the partial unique index only catches later),
    and no second row is created."""
    from backend.app.core.db import SessionLocal
    from backend.app.services import enrollment as enrollment_service
    from backend.app.core.errors import ApiError
    from backend.app.core.codes import ErrorCode
    from backend.app.models import BootstrapToken
    from backend.tests.test_operator_auth import _seed_operator

    admin = _admin(client, db_session)
    first = _issue(client, admin, "race-host")
    assert first.status_code == 201

    # Simulate a concurrent issuer holding its own session/transaction.
    concurrency_db = SessionLocal()
    try:
        class _Op:
            username = "admin"

        _Op.id = _seed_operator(db_session).id
        with pytest.raises(ApiError) as excinfo:
            enrollment_service.issue_bootstrap_token(concurrency_db, _Op, "race-host")
        assert excinfo.value.status == 409
        assert excinfo.value.code == ErrorCode.BOOTSTRAP_TOKEN_ACTIVE
    finally:
        concurrency_db.rollback()
        concurrency_db.close()

    # Exactly one active token row exists for the hostname.
    rows = db_session.query(BootstrapToken).filter(BootstrapToken.hostname == "race-host").all()
    assert len(rows) == 1


def test_concurrent_issue_race_window_before_any_commit(client, db_session):
    """True race window: two issuers on the same hostname inside one open
    transaction. The second issuance must fail closed with 409 via the
    pre-insert guard (never an IntegrityError/500, never two active rows),
    and the first row must survive the failed second call."""
    from backend.app.core.db import SessionLocal
    from backend.app.services import enrollment as enrollment_service
    from backend.app.core.errors import ApiError
    from backend.app.core.codes import ErrorCode
    from backend.app.models import BootstrapToken
    from backend.tests.test_operator_auth import _seed_operator

    class _Op:
        username = "admin"

    _Op.id = _seed_operator(db_session).id

    issuer = SessionLocal()
    try:
        # First issuance commits a still-active token.
        row_a, plaintext_a = enrollment_service.issue_bootstrap_token(issuer, _Op, "window-host")
        # Second issuance in the same session: an uncommitted-then-committed
        # active row is already visible; the pre-insert guard must 409 before
        # any INSERT, leaving exactly one row.
        with pytest.raises(ApiError) as excinfo:
            enrollment_service.issue_bootstrap_token(issuer, _Op, "window-host")
        assert excinfo.value.status == 409
        assert excinfo.value.code == ErrorCode.BOOTSTRAP_TOKEN_ACTIVE
        rows = issuer.query(BootstrapToken).filter(BootstrapToken.hostname == "window-host").all()
        assert len(rows) == 1
    finally:
        issuer.rollback()
        issuer.close()


# ------------------------------------------------------- B3/P6: ownership guard


def _seed_ownership(db_session, host_id: str, job_id: str, disposition: str = "HELD"):
    """Insert a full FK chain (machine → connection → target → validation →
    job → ownership) binding host_id to a job. FKs are DEFERRABLE so order
    within the transaction does not matter, but parent PKs must all exist at
    COMMIT."""
    import uuid as _uuid

    from backend.app.models import (
        ProvisioningConnection,
        ProvisioningJob,
        ProvisioningMachine,
        ProvisioningOwnership,
        ProvisioningTarget,
        ProvisioningValidation,
    )
    from backend.tests.test_operator_auth import _seed_operator

    actor_id = _seed_operator(db_session).id

    machine_id = f"mch-{job_id}"
    conn_id = f"con-{job_id}"
    target_id = f"tgt-{job_id}"
    validation_id = f"val-{job_id}"

    db_session.add(ProvisioningMachine(
        id=machine_id, machine_binding_hash=f"bind-{job_id}",
    ))
    db_session.add(ProvisioningConnection(
        id=conn_id, provider="GENERIC_LINUX", display_name=f"conn {job_id}",
        policy_hash="0" * 64,
    ))
    db_session.add(ProvisioningTarget(
        id=target_id, connection_id=conn_id, canonical_key=f"ck-{job_id}",
        host_id=host_id, mapping_status="MAPPED", mapping_revision=1,
    ))
    db_session.add(ProvisioningValidation(
        id=validation_id, target_id=target_id, actor_id=actor_id,
        plan_json="{}", plan_hash="0" * 64, config_revision=0, mapping_revision=0,
        observed_identity_hash="0" * 64, created_at=0,
        expires_at=9_999_999_999_999,
    ))
    db_session.add(ProvisioningJob(
        id=job_id, target_id=target_id, operation="INSTALL", expected_host_id=host_id,
        validation_id=validation_id, requester_id=actor_id,
        approval_hash="0" * 64, approval_expires_at=9_999_999_999_999,
        plan_json="{}", deadline_at=9_999_999_999_999, created_at=0, updated_at=0,
    ))
    row = ProvisioningOwnership(
        target_id=target_id, host_id=host_id, owner_job_id=job_id,
        generation=1, disposition=disposition, acquired_at=0,
    )
    db_session.add(row)
    db_session.commit()
    return row


def _seed_host_row(db_session, hostname: str):
    """Insert a bare Host row and return its id."""
    from datetime import datetime, timezone

    from backend.app.models import Host

    host = Host(
        hostname=hostname,
        agent_token_hash="0" * 64,
        enrolled_at=datetime.now(timezone.utc),
    )
    db_session.add(host)
    db_session.commit()
    return host.id


def test_issue_blocked_while_ownership_held(client, db_session):
    """B3: bootstrap token issuance must be refused while a provisioning job
    holds ownership of the target host (409 TARGET_ALREADY_MANAGED)."""
    from backend.app.core.codes import ErrorCode

    admin = _admin(client, db_session)
    host_id = _seed_host_row(db_session, "owned-host")
    _seed_ownership(db_session, host_id, "job-1", "HELD")

    resp = _issue(client, admin, "owned-host")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == ErrorCode.TARGET_ALREADY_MANAGED

    # No token row may have been created.
    from backend.app.models import BootstrapToken

    assert db_session.query(BootstrapToken).filter(BootstrapToken.hostname == "owned-host").count() == 0


def test_issue_blocked_while_ownership_reconciling(client, db_session):
    """RECONCILING ownership (post-failure repair in flight) also fences issuance."""
    from backend.app.core.codes import ErrorCode

    admin = _admin(client, db_session)
    host_id = _seed_host_row(db_session, "recon-host")
    _seed_ownership(db_session, host_id, "job-2", "RECONCILING")

    resp = _issue(client, admin, "recon-host")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == ErrorCode.TARGET_ALREADY_MANAGED


def test_issue_allowed_after_ownership_released(client, db_session):
    """A RELEASED ownership row (job done/cancelled) does NOT fence issuance —
    the row survives release (§5) but the host can be re-onboarded."""
    admin = _admin(client, db_session)
    host_id = _seed_host_row(db_session, "freed-host")
    _seed_ownership(db_session, host_id, "job-3", "RELEASED")

    resp = _issue(client, admin, "freed-host")
    assert resp.status_code == 201, resp.text
    assert resp.json()["token"]


def test_issue_allowed_for_unknown_hostname(client, db_session):
    """A brand-new hostname (no Host row) has no ownership to check — issuance
    proceeds. This keeps fresh onboarding unaffected by the guard."""
    admin = _admin(client, db_session)
    resp = _issue(client, admin, "brand-new-host")
    assert resp.status_code == 201, resp.text


def test_reenroll_issue_blocked_while_ownership_held(client, db_session):
    """P6: re-enroll bootstrap tokens are fenced by the same ownership guard."""
    from backend.app.core.codes import ErrorCode

    admin = _admin(client, db_session)
    host_id = _seed_host_row(db_session, "re-enroll-owned")
    _seed_ownership(db_session, host_id, "job-4", "HELD")

    resp = _issue(client, admin, "re-enroll-owned", intent="reenroll")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == ErrorCode.TARGET_ALREADY_MANAGED
