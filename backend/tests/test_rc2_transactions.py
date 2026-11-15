"""RC2 F07: transactional invariants.

Covers:
- stale result fencing across a re-claim (a delayed result from an expired
  claim must never win),
- single-winner result recording under concurrent submissions,
- concurrent deployment deduplication (one in-flight operation per deployment),
- bootstrap token is not burned when host creation fails.
"""

import threading

from sqlalchemy import func, select

from backend.app.core.db import SessionLocal
from backend.app.models import BootstrapToken, DeploymentOperation, Host
from backend.app.services import deployments as deployments_service
from backend.tests.conftest import auth_headers
from backend.tests.test_bootstrap_enrollment import _admin, _issue
from backend.tests.test_deployments import deploy


def _force_timeout(operation_id: str) -> None:
    from datetime import datetime, timedelta, timezone

    db = SessionLocal()
    try:
        op = db.get(DeploymentOperation, operation_id)
        op.timeout_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()


def _poll(client, host_id, token):
    return client.post("/api/v1/agents/commands/poll", headers=auth_headers(host_id, token)).json()["commands"]


def test_stale_result_from_expired_claim_is_fenced(client, online_host):
    host_id, token = online_host
    op_id = deploy(client, host_id).json()["operation_id"]

    first = _poll(client, host_id, token)
    assert len(first) == 1
    stale_generation = first[0]["claim_generation"]
    assert stale_generation == 1

    # Claim expires and the operation is re-delivered to a new attempt.
    _force_timeout(op_id)
    second = _poll(client, host_id, token)
    assert len(second) == 1
    fresh_generation = second[0]["claim_generation"]
    assert fresh_generation == 2

    # A delayed result from the expired claim must be rejected and must not
    # terminate the operation.
    stale = client.post(
        f"/api/v1/agents/commands/{op_id}/result",
        json={"status": "SUCCEEDED", "claim_generation": stale_generation},
        headers=auth_headers(host_id, token),
    )
    assert stale.status_code == 200
    assert stale.json()["accepted"] is False

    db = SessionLocal()
    try:
        assert db.get(DeploymentOperation, op_id).status == "RUNNING"
    finally:
        db.close()

    # The current claim can still report.
    fresh = client.post(
        f"/api/v1/agents/commands/{op_id}/result",
        json={"status": "SUCCEEDED", "claim_generation": fresh_generation},
        headers=auth_headers(host_id, token),
    )
    assert fresh.json()["accepted"] is True
    assert fresh.json()["status"] == "SUCCEEDED"


def test_concurrent_results_have_one_winner(client, online_host):
    host_id, token = online_host
    op_id = deploy(client, host_id).json()["operation_id"]
    _poll(client, host_id, token)

    outcomes: list[bool] = []
    lock = threading.Lock()

    def submit(status: str):
        resp = client.post(
            f"/api/v1/agents/commands/{op_id}/result",
            json={"status": status, "result": {"container_state": "RUNNING"}},
            headers=auth_headers(host_id, token),
        )
        with lock:
            outcomes.append(resp.json()["accepted"])

    threads = [threading.Thread(target=submit, args=(s,)) for s in ("SUCCEEDED", "FAILED")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(outcomes) == [False, True]

    db = SessionLocal()
    try:
        op = db.get(DeploymentOperation, op_id)
        assert op.status in ("SUCCEEDED", "FAILED")
        # Duplicate delivery is idempotent and never overwrites evidence.
        assert deployments_service.submit_result(
            db, host_id, op_id, _result("UNKNOWN")
        )[1] is False
    finally:
        db.close()


class _result:
    def __init__(self, status):
        self.status = status
        self.result = None
        self.error_code = None
        self.error_message = None
        self.claim_generation = None


def test_concurrent_deploy_creates_one_operation(client, online_host):
    host_id, _ = online_host
    from backend.tests.test_docker_authz import _login_admin, _patch_docker

    admin = _login_admin(client)
    _patch_docker(client, admin, host_id, True)

    bodies: list[dict] = []
    lock = threading.Lock()

    def submit():
        resp = client.post(
            "/api/v1/applications/deploy",
            json={"host_id": host_id, "template_key": "nginx-demo"},
            headers={"Authorization": f"Bearer {admin}"},
        )
        with lock:
            bodies.append(resp.json())

    threads = [threading.Thread(target=submit) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len({b["operation_id"] for b in bodies}) == 1
    db = SessionLocal()
    try:
        count = db.scalar(
            select(func.count())
            .select_from(DeploymentOperation)
            .where(
                DeploymentOperation.host_id == host_id,
                DeploymentOperation.status.in_(("QUEUED", "RUNNING")),
            )
        )
        assert count == 1
    finally:
        db.close()


def test_bootstrap_token_survives_host_creation_failure(client, db_session, monkeypatch):
    admin = _admin(client, db_session)
    tok = _issue(client, admin, "atomic-host").json()["token"]

    from backend.app.api import agents as agents_api
    from backend.app.core.codes import ErrorCode
    from backend.app.core.errors import ApiError

    def boom(*_args, **_kwargs):
        raise ApiError(500, ErrorCode.INTERNAL, "simulated host-creation failure")

    monkeypatch.setattr(agents_api.host_service, "enroll_host", boom)

    resp = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "atomic-host", "bootstrap_token": tok},
    )
    assert resp.status_code == 500

    db = SessionLocal()
    try:
        row = db.scalar(select(BootstrapToken).where(BootstrapToken.hostname == "atomic-host"))
        assert row is not None
        assert row.consumed_at is None, "token was burned despite failed host creation"
        assert db.scalar(select(Host).where(Host.hostname == "atomic-host")) is None
    finally:
        db.close()
