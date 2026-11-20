"""Regression coverage for the independent Session 2 review."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.app.models import BootstrapToken, Host, HostEvent
from backend.app.services.host_lifecycle import revoke_host
from backend.tests.test_bootstrap_enrollment import _admin, _issue
from backend.tests.test_bootstrap_intent import _seed_ownership


def test_every_revoke_has_revision_audit_and_invalidates_new_bootstrap(client, db_session, online_host):
    host_id, _ = online_host
    host = db_session.get(Host, host_id)
    admin = _admin(client, db_session)
    for revision in (1, 2):
        issued = _issue(client, admin, host.hostname, intent="reenroll")
        assert issued.status_code == 201
        revoke_host(db_session, host_id, "admin")
        row = db_session.scalar(select(BootstrapToken).where(BootstrapToken.id == issued.json()["id"]))
        assert row.revoked_at is not None
        events = db_session.scalars(select(HostEvent).where(
            HostEvent.host_id == host_id, HostEvent.event == "HOST_REVOKED",
        )).all()
        assert len(events) == revision
        assert f"revision={revision}" in events[-1].detail


def test_reenroll_clears_previous_credential_grace(client, db_session, online_host):
    host_id, _ = online_host
    host = db_session.get(Host, host_id)
    host.previous_token_hash = "a" * 64
    host.previous_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    db_session.commit()
    admin = _admin(client, db_session)
    issued = _issue(client, admin, host.hostname, intent="reenroll")
    assert issued.status_code == 201
    response = client.post("/api/v1/agents/enroll", json={
        "hostname": host.hostname, "bootstrap_token": issued.json()["token"],
    })
    assert response.status_code == 200
    db_session.refresh(host)
    assert host.previous_token_hash is None
    assert host.previous_token_expires_at is None


def test_revoke_invalidates_grants_bound_through_target(client, db_session, online_host):
    from backend.app.models import ProvisioningGrant

    host_id, _ = online_host
    owner = _seed_ownership(db_session, host_id, "revocation-job", "RELEASED")
    grant = ProvisioningGrant(
        job_id=owner.owner_job_id, dispatch_id=owner.owner_job_id,
        target_id=owner.target_id, intent="INSTALL", token_hash="b" * 64,
        expires_at=9_999_999_999_999,
    )
    db_session.add(grant)
    db_session.commit()
    revoke_host(db_session, host_id, "admin")
    db_session.refresh(grant)
    assert grant.revoked_at is not None
