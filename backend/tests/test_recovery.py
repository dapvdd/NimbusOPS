"""Task 4: claim-timeout recovery tests (restart hardening).

Covers PHASE3B_IMPLEMENTATION_PLAN.md Task 4:
- A RUNNING op past its `timeout_at` returns to QUEUED on reconcile and is
  re-delivered on the next poll.
- Reconcile is idempotent (second run touches nothing).
- Ops with terminal results are never touched.
- Ops still within their claim window are left RUNNING.
- Restart mid-enrollment: bootstrap tokens and operator sessions survive a
  full app restart (they are durable rows, not in-memory state).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.app.core.db import SessionLocal
from backend.app.models import DeploymentOperation
from backend.tests.test_operator_auth import _seed_operator


def _deploy(client, host_id: str) -> str:
    from backend.tests.test_docker_authz import _login_admin, _patch_docker

    admin = _login_admin(client)
    assert _patch_docker(client, admin, host_id, True).status_code == 200
    resp = client.post(
        "/api/v1/applications/deploy",
        headers={"Authorization": f"Bearer {admin}"},
        json={"host_id": host_id, "template_key": "nginx-demo"},
    )
    assert resp.status_code == 202, resp.text
    return resp.json()["operation_id"]


def _poll(client, headers) -> list:
    resp = client.post("/api/v1/agents/commands/poll", headers=headers, json={})
    assert resp.status_code == 200, resp.text
    return resp.json()["commands"]


def _force_timeout(operation_id: str, seconds: int = 1) -> None:
    db = SessionLocal()
    try:
        op = db.get(DeploymentOperation, operation_id)
        op.timeout_at = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        db.commit()
    finally:
        db.close()


def test_running_op_past_timeout_returns_to_queued_and_redelivers(client, online_host):
    from backend.app.services.deployments import reconcile_timed_out_ops

    host_id, token = online_host
    headers = {"X-Host-Id": host_id, "Authorization": f"Bearer {token}"}
    op_id = _deploy(client, host_id)

    # Claim it (QUEUED -> RUNNING, timeout_at stamped).
    cmds = _poll(client, headers)
    assert len(cmds) == 1 and cmds[0]["id"] == op_id
    db = SessionLocal()
    try:
        assert db.get(DeploymentOperation, op_id).status == "RUNNING"
    finally:
        db.close()

    # Agent goes silent past the deadline; reconcile re-queues.
    _force_timeout(op_id)
    n = reconcile_timed_out_ops()
    assert n == 1
    db = SessionLocal()
    try:
        op = db.get(DeploymentOperation, op_id)
        assert op.status == "QUEUED"
        assert op.claimed_at is None  # claim released
    finally:
        db.close()

    # Re-delivered on next poll (exactly-once semantics preserved per claim).
    cmds = _poll(client, headers)
    assert len(cmds) == 1 and cmds[0]["id"] == op_id


def test_reconcile_is_idempotent_and_skips_fresh_running(client, online_host):
    from backend.app.services.deployments import reconcile_timed_out_ops

    host_id, token = online_host
    headers = {"X-Host-Id": host_id, "Authorization": f"Bearer {token}"}
    op_id = _deploy(client, host_id)
    _poll(client, headers)  # RUNNING with fresh timeout_at

    assert reconcile_timed_out_ops() == 0  # within window: untouched
    assert reconcile_timed_out_ops() == 0  # idempotent: nothing to do twice

    db = SessionLocal()
    try:
        assert db.get(DeploymentOperation, op_id).status == "RUNNING"
    finally:
        db.close()


def test_terminal_ops_never_touched(client, online_host):
    from backend.app.services.deployments import reconcile_timed_out_ops

    host_id, token = online_host
    headers = {"X-Host-Id": host_id, "Authorization": f"Bearer {token}"}
    op_id = _deploy(client, host_id)
    _poll(client, headers)
    # Agent reports success (terminal evidence).
    resp = client.post(
        f"/api/v1/agents/commands/{op_id}/result",
        headers=headers,
        json={"status": "SUCCEEDED", "result": {"verified": True}},
    )
    assert resp.status_code == 200
    _force_timeout(op_id)

    assert reconcile_timed_out_ops() == 0
    db = SessionLocal()
    try:
        op = db.get(DeploymentOperation, op_id)
        assert op.status == "SUCCEEDED"
    finally:
        db.close()


def test_bootstrap_tokens_and_sessions_survive_restart(client, db_session):
    """Rows are durable: a fresh app instance sees the same token/session."""
    _seed_operator(db_session)
    login = client.post("/api/v1/operators/login", json={"username": "admin", "password": "secret-pw"})
    admin = login.json()["session_token"]
    issue = client.post(
        "/api/v1/operators/bootstrap-tokens",
        headers={"Authorization": f"Bearer {admin}"},
        json={"hostname": "restart-host"},
    )
    assert issue.status_code == 201
    token = issue.json()["token"]

    # Simulate restart: same DB, brand-new app instance.
    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    with TestClient(create_app()) as fresh_client:
        me = fresh_client.get("/api/v1/operators/me", headers={"Authorization": f"Bearer {admin}"})
        assert me.status_code == 200
        enroll = fresh_client.post(
            "/api/v1/agents/enroll",
            json={"hostname": "restart-host", "bootstrap_token": token},
        )
        assert enroll.status_code == 200
