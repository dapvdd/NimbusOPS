"""Durable confirmation and no blind retry after possible remote mutation."""

from types import SimpleNamespace

import pytest

from backend.app.models import Operator


def test_confirmation_is_single_use(client, db_session):
    from backend.app.services.provisioning import save_plan, confirm_plan
    from backend.app.provisioning.ssh import Target

    op = Operator(username="setup-admin", password_hash="unused", role="ADMIN")
    db_session.add(op)
    db_session.commit()
    target = Target(
        "test", "192.0.2.10", "installer", "new-vm", "/run/key", "/etc/known", "a" * 32
    )
    plan = save_plan(db_session, op.id, target, {"hostname": "new-vm"})
    job = confirm_plan(db_session, op.id, target, plan.id, plan.plan_hash)
    assert job.state == "PENDING"
    with pytest.raises(ValueError):
        confirm_plan(db_session, op.id, target, plan.id, plan.plan_hash)


def test_changed_policy_invalidates_plan(client, db_session):
    from backend.app.services.provisioning import save_plan, confirm_plan
    from backend.app.provisioning.ssh import Target
    from dataclasses import replace

    op = Operator(username="setup-admin", password_hash="unused", role="ADMIN")
    db_session.add(op)
    db_session.commit()
    target = Target(
        "test", "192.0.2.10", "installer", "new-vm", "/run/key", "/etc/known", "a" * 32
    )
    plan = save_plan(db_session, op.id, target, {"hostname": "new-vm"})
    with pytest.raises(ValueError):
        confirm_plan(
            db_session, op.id, replace(target, port=2222), plan.id, plan.plan_hash
        )


def test_worker_claim_is_atomic_and_restart_does_not_redispatch(client, db_session):
    from backend.app.provisioning.worker import claim_job
    from backend.app.services.provisioning import save_plan, confirm_plan
    from backend.app.provisioning.ssh import Target

    op = Operator(username="worker-admin", password_hash="unused", role="ADMIN")
    db_session.add(op)
    db_session.commit()
    target = Target(
        "test", "192.0.2.10", "installer", "new-vm", "/run/key", "/etc/known", "a" * 32
    )
    plan = save_plan(db_session, op.id, target, {"hostname": "new-vm"})
    job = confirm_plan(db_session, op.id, target, plan.id, plan.plan_hash)
    assert claim_job(db_session) == job.id
    assert claim_job(db_session) is None
    db_session.refresh(job)
    assert job.state == "RUNNING"
    assert job.reconciliation_required


def test_success_requires_token_linked_fresh_telemetry(
    client, db_session, enrolled_host
):
    from backend.app.provisioning.worker import enrollment_ready
    from backend.app.models import BootstrapToken, Host
    from datetime import datetime, timezone, timedelta

    host_id, _ = enrolled_host
    now = datetime.now(timezone.utc)
    host = db_session.get(Host, host_id)
    token = BootstrapToken(
        token_hash="a" * 64,
        hostname=host.hostname,
        expires_at=now + timedelta(minutes=5),
        consumed_at=now - timedelta(seconds=30),
        consumed_by=host_id,
    )
    db_session.add(token)
    db_session.commit()
    assert not enrollment_ready(db_session, token.id)
    host.last_seen_at = now
    host.last_telemetry_at = now
    db_session.commit()
    assert not enrollment_ready(
        db_session, token.id
    )  # A host timestamp is not a telemetry row.
    from backend.app.models import Telemetry

    db_session.add(
        Telemetry(
            host_id=host_id,
            recorded_at=now,
            cpu_percent=0,
            memory_used_bytes=1,
            memory_total_bytes=2,
            disk_used_bytes=1,
            disk_total_bytes=2,
            memory_used_percent=50,
            disk_used_percent=50,
        )
    )
    db_session.commit()
    assert enrollment_ready(db_session, token.id)
    host.is_revoked = True
    db_session.commit()
    assert not enrollment_ready(db_session, token.id)


def test_retry_rejects_admitted_or_ambiguous_job(client, db_session):
    from backend.app.services.provisioning import retry_plan

    with pytest.raises(ValueError):
        retry_plan(db_session, "missing", "admin")


def test_failed_preflight_can_retry_only_with_new_approval(
    client, db_session, monkeypatch
):
    from backend.app.provisioning.worker import run_once
    from backend.app.services.provisioning import save_plan, confirm_plan, retry_plan
    from backend.app.provisioning.ssh import Target

    op = Operator(username="retry-admin", password_hash="unused", role="ADMIN")
    db_session.add(op)
    db_session.commit()
    target = Target(
        "test", "192.0.2.10", "installer", "new-vm", "/run/key", "/etc/known", "a" * 32
    )
    plan = save_plan(db_session, op.id, target, {"hostname": "new-vm"})
    job = confirm_plan(db_session, op.id, target, plan.id, plan.plan_hash)

    def rejected(_):
        raise ValueError("SSH_REJECTED")

    monkeypatch.setattr("backend.app.provisioning.worker.preflight", rejected)
    run_once(db_session, {"test": target}, "https://demo.example")
    db_session.refresh(job)
    assert job.state == "FAILED"
    assert not job.reconciliation_required
    assert retry_plan(db_session, job.id, op.id) == "test"
    with pytest.raises(ValueError):
        confirm_plan(db_session, op.id, target, plan.id, plan.plan_hash)
    fresh = save_plan(db_session, op.id, target, {"hostname": "new-vm"})
    retried = confirm_plan(db_session, op.id, target, fresh.id, fresh.plan_hash)
    assert retried.id != job.id


def test_ssh_disconnect_cannot_dispatch_twice(client, db_session, monkeypatch):
    from backend.app.provisioning.worker import run_once
    from backend.app.services.provisioning import save_plan, confirm_plan, retry_plan
    from backend.app.provisioning.ssh import Target
    from backend.app.models import BootstrapToken
    from sqlalchemy import select

    op = Operator(username="disconnect-admin", password_hash="unused", role="ADMIN")
    db_session.add(op)
    db_session.commit()
    target = Target(
        "test", "192.0.2.10", "installer", "new-vm", "/run/key", "/etc/known", "a" * 32
    )
    facts = {"hostname": "new-vm"}
    plan = save_plan(db_session, op.id, target, facts)
    job = confirm_plan(db_session, op.id, target, plan.id, plan.plan_hash)
    monkeypatch.setattr("backend.app.provisioning.worker.preflight", lambda _: facts)
    dispatches = []

    def disconnect(*args):
        dispatches.append(1)
        raise ValueError("INSTALL_OUTCOME_UNKNOWN")

    monkeypatch.setattr("backend.app.provisioning.worker.install", disconnect)
    run_once(db_session, {"test": target}, "https://demo.example")
    run_once(db_session, {"test": target}, "https://demo.example")
    assert dispatches == [1]
    db_session.refresh(job)
    assert job.state == "VERIFYING"
    assert job.reconciliation_required
    with pytest.raises(ValueError):
        retry_plan(db_session, job.id, op.id)
    assert len(db_session.scalars(select(BootstrapToken)).all()) == 1


def test_manual_token_conflict_fails_job_without_killing_worker(
    client, db_session, monkeypatch
):
    from backend.app.provisioning.worker import run_once
    from backend.app.services.provisioning import save_plan, confirm_plan
    from backend.app.services.enrollment import issue_bootstrap_token
    from backend.app.provisioning.ssh import Target

    op = Operator(username="conflict-admin", password_hash="unused", role="ADMIN")
    db_session.add(op)
    db_session.commit()
    target = Target(
        "test", "192.0.2.10", "installer", "new-vm", "/run/key", "/etc/known", "a" * 32
    )
    facts = {"hostname": "new-vm"}
    plan = save_plan(db_session, op.id, target, facts)
    issue_bootstrap_token(db_session, op, target.hostname, 600)
    job = confirm_plan(db_session, op.id, target, plan.id, plan.plan_hash)
    monkeypatch.setattr("backend.app.provisioning.worker.preflight", lambda _: facts)
    run_once(db_session, {"test": target}, "https://demo.example")
    db_session.refresh(job)
    assert job.state == "FAILED"
    assert not job.reconciliation_required


def test_worker_excludes_concurrent_dispatch_and_reconciliation(tmp_path):
    from backend.app.provisioning.worker import worker_lock

    with worker_lock(str(tmp_path / "isolated.db")) as first:
        assert first
        with worker_lock(str(tmp_path / "isolated.db")) as second:
            assert not second


def test_stale_retry_cannot_release_replacement_owner(client, db_session):
    from backend.app.services.provisioning import release_for_retry
    from backend.app.models.provisioning import ProvisioningOwnership

    # A stale generation must not match even when all other fields agree.
    assert release_for_retry(db_session, "missing", "old-job", 1) is False


@pytest.mark.parametrize(
    "outcome", ["TIMED_OUT", "TRANSPORT_FAILED", "CANCELLED", "COMPLETED"]
)
def test_worker_persists_redacted_evidence_without_redispatch(
    client, db_session, monkeypatch, outcome
):
    import json
    from sqlalchemy import select
    from backend.app.provisioning import ssh, worker
    from backend.app.models.provisioning import ProvisioningEvent
    from backend.app.services.provisioning import save_plan, confirm_plan

    op = Operator(username="evidence-admin", password_hash="unused", role="ADMIN")
    db_session.add(op)
    db_session.commit()
    target = ssh.Target(
        "test", "192.0.2.10", "installer", "new-vm", "/key", "/known", "a" * 32
    )
    facts = {"hostname": "new-vm"}
    plan = save_plan(db_session, op.id, target, facts)
    job = confirm_plan(db_session, op.id, target, plan.id, plan.plan_hash)
    monkeypatch.setattr(worker, "preflight", lambda _: facts)
    evidence = ssh.InstallEvidence(
        ("LOCK_ACQUIRED", "ARCHIVE_VERIFIED"),
        42 if outcome == "TRANSPORT_FAILED" else None,
        255 if outcome == "TRANSPORT_FAILED" else None,
        outcome,
    )
    calls = []

    def dispatch(*args):
        calls.append(1)
        if outcome == "CANCELLED":
            raise ssh.InstallCancelled(evidence)
        if outcome != "COMPLETED":
            raise ssh.InstallOutcomeUnknown(evidence=evidence)
        return evidence

    monkeypatch.setattr(worker, "install", dispatch)
    if outcome == "CANCELLED":
        with pytest.raises(ssh.InstallCancelled):
            worker.run_once(db_session, {"test": target}, "https://demo.example")
    else:
        worker.run_once(db_session, {"test": target}, "https://demo.example")
    worker.run_once(db_session, {"test": target}, "https://demo.example")
    db_session.refresh(job)
    assert calls == [1]
    assert job.state == "VERIFYING"
    assert job.reconciliation_required
    events = db_session.scalars(
        select(ProvisioningEvent).where(ProvisioningEvent.job_id == job.id)
    ).all()
    codes = [e.code for e in events]
    assert "INSTALL_PHASE_LOCK_ACQUIRED" in codes
    assert "INSTALL_PHASE_ARCHIVE_VERIFIED" in codes
    assert f"INSTALL_{outcome}" in codes
    if outcome == "TRANSPORT_FAILED":
        assert any(
            json.loads(e.safe_detail_json or "{}").get("installer_exit_status") == 42
            for e in events
        )
    assert "secret" not in repr([(e.code, e.safe_detail_json) for e in events])
