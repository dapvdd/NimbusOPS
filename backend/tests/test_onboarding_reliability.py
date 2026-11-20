"""Regression gates for confirmation recovery and shared onboarding ownership."""

import pytest
import multiprocessing
from sqlalchemy import func, select

from backend.app.models import Operator
from backend.app.models.provisioning import ProvisioningJob, ProvisioningRequest
from backend.app.provisioning.ssh import Target
from backend.app.services.provisioning import confirm_plan, save_plan


@pytest.fixture
def setup_plan(client, db_session):
    actor = Operator(username="reliability-admin", password_hash="unused", role="ADMIN")
    other = Operator(username="other-admin", password_hash="unused", role="ADMIN")
    db_session.add_all([actor, other])
    db_session.commit()
    target = Target(
        "reliable",
        "192.0.2.10",
        "installer",
        "reliable-vm",
        "/run/key",
        "/etc/known",
        "a" * 32,
    )
    plan = save_plan(db_session, actor.id, target, {"hostname": target.hostname})
    return actor, other, target, plan


def test_confirmation_replay_returns_committed_job_after_expiry(db_session, setup_plan):
    actor, _, target, plan = setup_plan
    job = confirm_plan(
        db_session,
        actor.id,
        target,
        plan.id,
        plan.plan_hash,
        idempotency_key="stable-confirmation",
    )
    plan.expires_at = 0
    db_session.commit()
    recovered = confirm_plan(
        db_session,
        actor.id,
        target,
        plan.id,
        plan.plan_hash,
        idempotency_key="stable-confirmation",
    )
    assert recovered.id == job.id
    assert db_session.scalar(select(func.count()).select_from(ProvisioningJob)) == 1
    request = db_session.get(
        ProvisioningRequest, (actor.id, "ssh-confirm", "stable-confirmation")
    )
    assert request.job_id == job.id


def test_key_payload_mismatch_and_other_actor_rejected(db_session, setup_plan):
    actor, other, target, plan = setup_plan
    job = confirm_plan(
        db_session,
        actor.id,
        target,
        plan.id,
        plan.plan_hash,
        idempotency_key="stable-confirmation",
    )
    with pytest.raises(ValueError):
        confirm_plan(
            db_session,
            actor.id,
            target,
            plan.id,
            "b" * 64,
            idempotency_key="stable-confirmation",
        )
    with pytest.raises(ValueError):
        confirm_plan(
            db_session,
            other.id,
            target,
            plan.id,
            plan.plan_hash,
            idempotency_key="stable-confirmation",
        )
    assert db_session.get(ProvisioningJob, job.id).requester_id == actor.id


def test_recovery_requires_requester_and_survives_policy_removal(
    client, db_session, setup_plan, monkeypatch
):
    from backend.app.api import provisioning
    from backend.app.main import app

    actor, other, target, plan = setup_plan
    monkeypatch.setattr(provisioning, "configured_targets", lambda: {target.id: target})
    app.dependency_overrides[provisioning.admin] = lambda: actor
    payload = dict(
        target_id=target.id,
        validation_id=plan.id,
        approval_hash=plan.plan_hash,
        confirmed=True,
        idempotency_key="stable-confirmation",
    )
    try:
        # Discard the first response, just as a connection loss after commit would.
        first = client.post("/api/v1/provisioning/confirm", json=payload)
        assert first.status_code == 202
        job_id = first.json()["id"]
        monkeypatch.setattr(provisioning, "configured_targets", lambda: {})
        replay = client.post("/api/v1/provisioning/confirm", json=payload)
        assert replay.status_code == 202
        assert replay.json()["id"] == job_id
        path = "/api/v1/provisioning/requests/stable-confirmation"
        assert client.get(path).json()["id"] == job_id
        app.dependency_overrides[provisioning.admin] = lambda: other
        assert client.get(path).status_code == 404
        assert client.get(f"/api/v1/provisioning/jobs/{job_id}").status_code == 404
        assert client.post(f"/api/v1/provisioning/jobs/{job_id}/retry").status_code in (
            404,
            409,
        )
    finally:
        app.dependency_overrides.clear()
    assert client.get(path).status_code == 401


def test_automatic_reservation_blocks_manual_issue_and_old_token_consumption(
    db_session, setup_plan
):
    from backend.app.services.enrollment import (
        issue_bootstrap_token,
        consume_bootstrap_token,
    )
    from backend.app.core.errors import ApiError

    actor, _, target, plan = setup_plan
    _, plaintext = issue_bootstrap_token(db_session, actor, target.hostname)
    confirm_plan(db_session, actor.id, target, plan.id, plan.plan_hash)
    with pytest.raises(ApiError) as error:
        consume_bootstrap_token(db_session, plaintext, target.hostname)
    assert error.value.code == "TARGET_ALREADY_MANAGED"
    with pytest.raises(ApiError):
        issue_bootstrap_token(db_session, actor, target.hostname)


def test_automatic_enrollment_binds_host_before_reconciliation(
    client, db_session, setup_plan, monkeypatch
):
    from backend.app.provisioning.worker import run_once
    from backend.app.models import Host, BootstrapToken
    from backend.app.models.provisioning import (
        ProvisioningOwnership,
        ProvisioningTarget,
    )
    from backend.app.services.enrollment import issue_bootstrap_token
    from backend.app.core.errors import ApiError

    actor, _, target, plan = setup_plan
    job = confirm_plan(db_session, actor.id, target, plan.id, plan.plan_hash)
    monkeypatch.setattr(
        "backend.app.provisioning.worker.preflight",
        lambda _: {"hostname": target.hostname},
    )
    response = []

    def install(_target, _origin, plaintext):
        response.append(
            client.post(
                "/api/v1/agents/enroll",
                json={
                    "hostname": target.hostname,
                    "bootstrap_token": plaintext,
                    "agent_version": "test",
                },
            )
        )

    monkeypatch.setattr("backend.app.provisioning.worker.install", install)
    run_once(db_session, {target.id: target}, "https://test.example")
    assert len(response) == 1
    assert response[0].status_code == 200
    host_id = response[0].json()["host_id"]
    db_session.expire_all()
    ownership = db_session.get(ProvisioningOwnership, target.id)
    assert ownership.host_id == host_id
    assert db_session.get(ProvisioningTarget, target.id).host_id == host_id
    host = db_session.get(Host, host_id)
    original = (host.id, host.agent_token_hash, host.credential_version)
    with pytest.raises(ApiError):
        issue_bootstrap_token(db_session, actor, target.hostname, intent="reenroll")
    assert (host.id, host.agent_token_hash, host.credential_version) == original
    assert db_session.get(ProvisioningJob, job.id).state == "VERIFYING"


def test_stale_generation_rolls_back_enrollment_without_burning_token(
    client, db_session, setup_plan, monkeypatch
):
    import json
    from backend.app.provisioning.worker import run_once
    from backend.app.models import Host, BootstrapToken
    from backend.app.models.provisioning import ProvisioningOwnership

    actor, _, target, plan = setup_plan
    job = confirm_plan(db_session, actor.id, target, plan.id, plan.plan_hash)
    monkeypatch.setattr(
        "backend.app.provisioning.worker.preflight",
        lambda _: {"hostname": target.hostname},
    )
    plaintexts = []
    monkeypatch.setattr(
        "backend.app.provisioning.worker.install",
        lambda _t, _o, token: plaintexts.append(token),
    )
    run_once(db_session, {target.id: target}, "https://test.example")
    owner = db_session.get(ProvisioningOwnership, target.id)
    owner.disposition = "RELEASED"
    db_session.commit()
    response = client.post(
        "/api/v1/agents/enroll",
        json={
            "hostname": target.hostname,
            "bootstrap_token": plaintexts[0],
            "agent_version": "test",
        },
    )
    assert response.status_code == 409
    db_session.expire_all()
    assert (
        db_session.scalar(select(Host).where(Host.hostname == target.hostname)) is None
    )
    token = db_session.get(
        BootstrapToken, json.loads(job.plan_json)["bootstrap_token_id"]
    )
    assert token.consumed_at is None
    assert token.consumed_by is None


def test_different_targets_cannot_reserve_same_hostname(db_session, setup_plan):
    from dataclasses import replace

    actor, _, target, plan = setup_plan
    second = replace(target, id="second", machine_id="b" * 32)
    second_plan = save_plan(db_session, actor.id, second, {"hostname": target.hostname})
    confirm_plan(db_session, actor.id, target, plan.id, plan.plan_hash)
    with pytest.raises(ValueError):
        confirm_plan(
            db_session, actor.id, second, second_plan.id, second_plan.plan_hash
        )


def test_legacy_enrollment_cannot_bypass_automatic_reservation(db_session, setup_plan):
    from backend.app.services.hosts import enroll_host
    from backend.app.schemas import EnrollRequest
    from backend.app.core.errors import ApiError

    actor, _, target, plan = setup_plan
    confirm_plan(db_session, actor.id, target, plan.id, plan.plan_hash)
    with pytest.raises(ApiError):
        enroll_host(
            db_session, EnrollRequest(hostname=target.hostname, agent_version="test")
        )


def test_mixed_case_automatic_hostname_binds_canonical_identity(client, db_session, setup_plan, monkeypatch):
    from dataclasses import replace
    from backend.app.provisioning.worker import run_once
    from backend.app.models import Host
    from backend.app.models.provisioning import ProvisioningOwnership
    actor, _, original, _ = setup_plan
    target = replace(original, hostname="Mixed-VM")
    plan = save_plan(db_session, actor.id, target, {"hostname": target.hostname})
    confirm_plan(db_session, actor.id, target, plan.id, plan.plan_hash)
    monkeypatch.setattr("backend.app.provisioning.worker.preflight", lambda _: {"hostname": target.hostname})
    responses = []
    monkeypatch.setattr("backend.app.provisioning.worker.install", lambda _t, _o, token: responses.append(
        client.post("/api/v1/agents/enroll", json={"hostname": "Mixed-VM", "bootstrap_token": token})))
    run_once(db_session, {target.id: target}, "https://test.example")
    assert responses[0].status_code == 200
    db_session.expire_all()
    host = db_session.get(Host, responses[0].json()["host_id"])
    assert host.hostname == "mixed-vm"
    assert db_session.get(ProvisioningOwnership, target.id).host_id == host.id


def _confirm_process(url, actor_id, target, validation_id, approval_hash, start, queue):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(url, connect_args={"timeout": 30})
    try:
        start.wait(30)
        with Session(engine) as db:
            try:
                queue.put(
                    (
                        "ok",
                        confirm_plan(
                            db,
                            actor_id,
                            target,
                            validation_id,
                            approval_hash,
                            idempotency_key="concurrent-key",
                        ).id,
                    )
                )
            except Exception as exc:
                queue.put(("error", type(exc).__name__))
    finally:
        engine.dispose()


def _enroll_process(url, plaintext, hostname, pepper, start, queue):
    import os
    os.environ["NIMBUSOPS_TOKEN_PEPPER"] = pepper
    from backend.app.core.config import get_settings
    get_settings.cache_clear()
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from backend.app.services.enrollment import (
        consume_bootstrap_token,
        bind_bootstrap_host,
    )
    from backend.app.services.hosts import enroll_host
    from backend.app.schemas import EnrollRequest

    engine = create_engine(url, connect_args={"timeout": 30})
    try:
        start.wait(30)
        with Session(engine) as db:
            try:
                row = consume_bootstrap_token(db, plaintext, hostname, commit=False)
                host, _ = enroll_host(
                    db,
                    EnrollRequest(hostname=hostname, agent_version="test"),
                    via_bootstrap=True,
                    commit=False,
                )
                row.consumed_by = host.id
                bind_bootstrap_host(db, row, host)
                db.commit()
                queue.put(("ok", host.id))
            except Exception as exc:
                db.rollback()
                queue.put(("error", type(exc).__name__))
    finally:
        engine.dispose()


def test_independent_process_confirmations_return_one_job(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from backend.app.models import Base

    url = f"sqlite:///{(tmp_path / 'confirm.db').as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        actor = Operator(username="process-admin", password_hash="unused", role="ADMIN")
        db.add(actor)
        db.commit()
        target = Target(
            "process",
            "192.0.2.10",
            "installer",
            "process-vm",
            "/run/key",
            "/etc/known",
            "a" * 32,
        )
        plan = save_plan(db, actor.id, target, {"hostname": target.hostname})
        args = (url, actor.id, target, plan.id, plan.plan_hash)
    engine.dispose()
    context = multiprocessing.get_context("spawn")
    start, queue = context.Event(), context.Queue()
    children = [
        context.Process(target=_confirm_process, args=(*args, start, queue))
        for _ in range(4)
    ]
    try:
        for child in children:
            child.start()
        start.set()
        results = [queue.get(timeout=45) for _ in children]
        for child in children:
            child.join(30)
            assert child.exitcode == 0
        assert all(status == "ok" for status, _ in results), results
        assert len({job_id for _, job_id in results}) == 1
        with Session(create_engine(url)) as db:
            assert db.scalar(select(func.count()).select_from(ProvisioningJob)) == 1
            assert db.scalar(select(func.count()).select_from(ProvisioningRequest)) == 1
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join()
        queue.close()


@pytest.mark.parametrize("automatic", [False, True])
def test_independent_process_enrollment_consumes_once(tmp_path, automatic):
    import json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from backend.app.models import Base, Host, BootstrapToken
    from backend.app.models.provisioning import ProvisioningOwnership
    from backend.app.services.enrollment import issue_bootstrap_token
    from backend.app.core.config import get_settings
    settings = get_settings()
    pepper = settings.token_pepper or settings.enrollment_token

    url = f"sqlite:///{(tmp_path / 'enroll.db').as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        actor = Operator(username="process-admin", password_hash="unused", role="ADMIN")
        db.add(actor)
        db.commit()
        hostname = "process-vm"
        if automatic:
            target = Target(
                "process",
                "192.0.2.10",
                "installer",
                hostname,
                "/run/key",
                "/etc/known",
                "a" * 32,
            )
            plan = save_plan(db, actor.id, target, {"hostname": hostname})
            job = confirm_plan(db, actor.id, target, plan.id, plan.plan_hash)
            row, plaintext = issue_bootstrap_token(
                db,
                actor,
                hostname,
                commit=False,
                provisioning_job_id=job.id,
                ownership_generation=1,
            )
            job.plan_json = json.dumps(
                {
                    **json.loads(job.plan_json),
                    "bootstrap_token_id": row.id,
                    "ownership_generation": 1,
                }
            )
            db.commit()
        else:
            row, plaintext = issue_bootstrap_token(db, actor, hostname)
        token_id = row.id
    engine.dispose()
    context = multiprocessing.get_context("spawn")
    start, queue = context.Event(), context.Queue()
    children = [
        context.Process(
                target=_enroll_process, args=(url, plaintext, hostname, pepper, start, queue)
        )
        for _ in range(4)
    ]
    try:
        for child in children:
            child.start()
        start.set()
        results = [queue.get(timeout=45) for _ in children]
        for child in children:
            child.join(30)
            assert child.exitcode == 0
        assert [status for status, _ in results].count("ok") == 1, results
        assert all(
            status == "ok" or detail == "ApiError" for status, detail in results
        ), results
        with Session(create_engine(url)) as db:
            host = db.scalar(select(Host))
            assert db.scalar(select(func.count()).select_from(Host)) == 1
            assert host.credential_version == 1
            assert db.get(BootstrapToken, token_id).consumed_by == host.id
            if automatic:
                assert db.get(ProvisioningOwnership, "process").host_id == host.id
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join()
        queue.close()
