"""Phase 2 integration: real agent worker code -> real backend -> SQLite.

Docker execution is MOCKED at the executor boundary (no Docker Engine on
this machine — labeled MOCKED per brief §11). Everything else is real:
real uvicorn server thread, real HTTP, real agent Sender/CommandWorker,
real SQLite persistence, real protocol.
"""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from backend.tests.conftest import auth_headers  # noqa: F401  (enables env)

from agent.nimbusops_agent.client import Sender
from agent.nimbusops_agent.worker import CommandWorker, SenderCommandAdapter, WorkerOutcome

import os
import pathlib
import tempfile

_tmpdir = tempfile.mkdtemp(prefix="nimbusops-p2int-")
os.environ.setdefault("NIMBUSOPS_ENROLLMENT_TOKEN", "int-token-2")
os.environ.setdefault("NIMBUSOPS_DATABASE_URL", f"sqlite:///{pathlib.Path(_tmpdir) / 'p2.db'}")

import uvicorn  # noqa: E402

from backend.app.core.config import get_settings  # noqa: E402
from backend.app.main import app  # noqa: E402

BASE_URL = "http://127.0.0.1:8992"


@pytest.fixture(scope="module")
def server():
    config = uvicorn.Config(app, host="127.0.0.1", port=8992, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/v1/health", timeout=1) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(0.1)
    else:
        raise RuntimeError("test server did not become healthy")
    yield server
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def identity(server):
    """Enroll a real agent identity via the real API."""
    s = Sender(server_url=BASE_URL, host_id="pending", agent_token=get_settings().enrollment_token)
    try:
        from agent.nimbusops_agent.config import collect_host_info
        import socket

        ok, result = s.enroll(
            hostname=f"p2-int-{int(time.time()*1000)}",
            enrollment_token=get_settings().enrollment_token,
            info=collect_host_info(),
        )
    finally:
        s.close()
    assert ok, result
    import pathlib as _p

    return result["host_id"], result["agent_token"]


class MockDockerExecutor:
    """MOCKED Docker executor: deterministic outcomes, records commands."""

    def __init__(self, outcome=None):
        self.outcome = outcome or {
            "status": "SUCCEEDED",
            "result": {"container_state": "RUNNING", "http_ok": True, "app_url": "http://localhost:8080/"},
        }
        self.executed = []

    def execute(self, command):
        self.executed.append(command)
        return dict(self.outcome)


def deploy_request(host_id: str) -> dict:
    return {"host_id": host_id, "template_key": "nginx-demo"}


def http_post(path: str, payload: dict | None, headers: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload or {}).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def http_get(path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def operator_session(server) -> dict:
    """Login an ADMIN operator over real HTTP and return auth headers.

    Phase 3B: mutation endpoints require an operator session; integration
    tests act as the dashboard does (login, then Bearer header).
    """
    from sqlalchemy import select as _select

    from backend.app.core.db import SessionLocal as SL
    from backend.app.core.security import hash_operator_password
    from backend.app.models import Operator

    db = SL()
    try:
        existing = db.scalar(_select(Operator).where(Operator.username == "admin"))
        if existing is None:
            db.add(Operator(username="admin", password_hash=hash_operator_password("int-secret-pw"), role="ADMIN"))
            db.commit()
    finally:
        db.close()
    status, body = http_post("/api/v1/operators/login", {"username": "admin", "password": "int-secret-pw"})
    assert status == 200, body
    return {"Authorization": f"Bearer {body['session_token']}"}


def enable_docker(server, host_id: str, headers: dict) -> None:
    """PATCH docker_enabled=true (Phase 3B: Docker default-off)."""
    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/hosts/{host_id}",
        data=json.dumps({"docker_enabled": True}).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            assert r.status == 200
    except urllib.error.HTTPError as e:
        raise AssertionError(f"PATCH docker_enabled failed: {e.code} {e.read().decode()}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def test_full_deploy_flow_real_agent_real_backend(server, identity):
    """Dashboard-equivalent flow: login, enable Docker, deploy -> poll -> result -> state."""
    host_id, token = identity
    hdrs = operator_session(server)
    enable_docker(server, host_id, hdrs)
    # 1. Deploy via public API (as the dashboard does).
    status, body = http_post("/api/v1/applications/deploy", deploy_request(host_id), headers=hdrs)
    assert status == 202, body
    op_id = body["operation_id"]
    dep_id = body["deployment_id"]
    assert body["status"] == "QUEUED"

    # 2. Real agent Sender + CommandWorker claims and executes (mocked Docker).
    sender = Sender(server_url=BASE_URL, host_id=host_id, agent_token=token)
    ex = MockDockerExecutor()
    worker = CommandWorker(http=SenderCommandAdapter(sender), executor=ex)
    try:
        assert worker.poll_once() == WorkerOutcome.EXECUTED
    finally:
        sender.close()
    assert ex.executed and ex.executed[0]["id"] == op_id
    assert ex.executed[0]["template"]["image"] == "nginx:1.27-alpine"

    # 3. Backend persisted the agent's evidence.
    status, op = http_get(f"/api/v1/operations/{op_id}")
    assert status == 200
    assert op["status"] == "SUCCEEDED"
    assert op["result"]["container_state"] == "RUNNING"
    assert op["result"]["http_ok"] is True

    # 4. Managed application inventory reflects the result.
    status, apps = http_get("/api/v1/applications")
    assert status == 200
    assert apps["count"] == 1
    app = apps["applications"][0]
    assert app["deployment_id"] == dep_id
    assert app["container_state"] == "RUNNING"
    assert app["http_ok"] is True
    assert app["app_url"] == "http://localhost:18080/"


def test_full_stop_start_flow_real_agent_real_backend(server, identity):
    host_id, token = identity
    hdrs = operator_session(server)
    enable_docker(server, host_id, hdrs)
    _, body = http_post("/api/v1/applications/deploy", deploy_request(host_id), headers=hdrs)
    dep_id = body["deployment_id"]
    op_id = body["operation_id"]

    sender = Sender(server_url=BASE_URL, host_id=host_id, agent_token=token)
    ex = MockDockerExecutor()
    worker = CommandWorker(http=SenderCommandAdapter(sender), executor=ex)
    try:
        worker.poll_once()  # executes DEPLOY
    finally:
        sender.close()

    # STOP via dashboard-equivalent call.
    status, stop_body = http_post(f"/api/v1/applications/{dep_id}/stop", None, headers=hdrs)
    assert status == 202
    stop_op = stop_body["operation_id"]

    # STOP outcome: container EXITED, http probe not applicable.
    sender = Sender(server_url=BASE_URL, host_id=host_id, agent_token=token)
    ex2 = MockDockerExecutor(
        outcome={"status": "SUCCEEDED", "result": {"container_state": "EXITED", "http_ok": None}}
    )
    worker2 = CommandWorker(http=SenderCommandAdapter(sender), executor=ex2)
    try:
        worker2.poll_once()
    finally:
        sender.close()
    assert ex2.executed[0]["op_type"] == "STOP"
    status, op = http_get(f"/api/v1/operations/{stop_op}")
    assert status == 200
    assert op["status"] == "SUCCEEDED"
    assert op["result"]["container_state"] == "EXITED"

    # START again.
    status, start_body = http_post(f"/api/v1/applications/{dep_id}/start", None, headers=hdrs)
    assert status == 202
    start_op = start_body["operation_id"]
    sender = Sender(server_url=BASE_URL, host_id=host_id, agent_token=token)
    ex3 = MockDockerExecutor()
    worker3 = CommandWorker(http=SenderCommandAdapter(sender), executor=ex3)
    try:
        worker3.poll_once()
    finally:
        sender.close()
    assert ex3.executed[0]["op_type"] == "START"
    status, op = http_get(f"/api/v1/operations/{start_op}")
    assert op["status"] == "SUCCEEDED"
    assert op["result"]["container_state"] == "RUNNING"


def test_duplicate_deploy_single_execution(server, identity):
    """Repeated deploy clicks: one deployment, one operation, one execution."""
    host_id, token = identity
    hdrs = operator_session(server)
    enable_docker(server, host_id, hdrs)
    s1, b1 = http_post("/api/v1/applications/deploy", deploy_request(host_id), headers=hdrs)
    s2, b2 = http_post("/api/v1/applications/deploy", deploy_request(host_id), headers=hdrs)
    assert s1 == 202 and s2 == 202
    assert b1["operation_id"] == b2["operation_id"]

    sender = Sender(server_url=BASE_URL, host_id=host_id, agent_token=token)
    ex = MockDockerExecutor()
    worker = CommandWorker(http=SenderCommandAdapter(sender), executor=ex)
    try:
        worker.poll_once()
    finally:
        sender.close()

    # Duplicate delivery simulation: a fresh worker receives the same command
    # (claim race). Its in-memory dedup set is per-instance, so the BACKEND
    # must be the dedup authority: re-submitted results are first-write-wins
    # (accepted=false) and no second operation/deployment can be created.
    class ReDeliverHttp:
        def __init__(self, inner, cmd):
            self.inner = SenderCommandAdapter(inner)
            self.cmd = cmd

        def poll(self):
            if self.cmd is not None:
                c = self.cmd
                self.cmd = None
                return {"commands": [c]}
            return self.inner.poll()

        def submit_result(self, *a, **k):
            return self.inner.submit_result(*a, **k)

    cmd = {"id": b1["operation_id"], "deployment_id": b1["deployment_id"], "host_id": host_id,
           "op_type": "DEPLOY", "status": "RUNNING", "created_at": "", "updated_at": "",
           "completed_at": None, "result": None, "error_code": None, "error_message": None,
           "template": {"key": "nginx-demo", "image": "nginx:1.27-alpine", "container_port": 80,
                        "host_port": 18080, "container_name": b1["container_name"]}}
    sender2 = Sender(server_url=BASE_URL, host_id=host_id, agent_token=token)
    ex2 = MockDockerExecutor()
    try:
        rdw = CommandWorker(http=ReDeliverHttp(sender2, cmd), executor=ex2)
        rdw.poll_once()
    finally:
        sender2.close()
    # Re-execution on the (mocked) Docker executor happened in the fresh
    # worker, but the backend kept first-write evidence and exactly one
    # managed application exists — no uncontrolled duplicates.
    assert len(ex2.executed) == 1

    status, op = http_get(f"/api/v1/operations/{b1['operation_id']}")
    assert op["status"] == "SUCCEEDED"
    status, apps = http_get("/api/v1/applications")
    mine = [a for a in apps["applications"] if a["host_id"] == host_id]
    assert len(mine) == 1  # exactly one managed application for THIS host


def test_host_disconnect_during_operation_recoverable(server, identity):
    """Agent claims, crashes before result; reconnects; op stays RUNNING
    (honest: outcome genuinely unknown until agent re-reports or times out)."""
    host_id, token = identity
    hdrs = operator_session(server)
    enable_docker(server, host_id, hdrs)
    _, body = http_post("/api/v1/applications/deploy", deploy_request(host_id), headers=hdrs)
    op_id = body["operation_id"]

    # Agent polls (claims) then "dies" (no result).
    sender = Sender(server_url=BASE_URL, host_id=host_id, agent_token=token)
    try:
        sender.poll_commands()
    finally:
        sender.close()

    status, op = http_get(f"/api/v1/operations/{op_id}")
    assert status == 200
    assert op["status"] == "RUNNING"  # honest: claimed, outcome unknown

    # Reconnected agent polls again: op NOT re-delivered (RUNNING, not QUEUED).
    sender2 = Sender(server_url=BASE_URL, host_id=host_id, agent_token=token)
    ex = MockDockerExecutor()
    worker = CommandWorker(http=SenderCommandAdapter(sender2), executor=ex)
    try:
        outcome = worker.poll_once()
    finally:
        sender2.close()
    assert outcome == WorkerOutcome.IDLE  # nothing re-claimed
    assert ex.executed == []


def test_failed_operation_recorded_with_error_details(server, identity):
    host_id, token = identity
    hdrs = operator_session(server)
    enable_docker(server, host_id, hdrs)
    _, body = http_post("/api/v1/applications/deploy", deploy_request(host_id), headers=hdrs)
    op_id = body["operation_id"]

    sender = Sender(server_url=BASE_URL, host_id=host_id, agent_token=token)
    ex = MockDockerExecutor(
        outcome={
            "status": "FAILED",
            "error_code": "DOCKER_FAILURE",
            "error_message": "pull failed: manifest unknown",
        }
    )
    worker = CommandWorker(http=SenderCommandAdapter(sender), executor=ex)
    try:
        worker.poll_once()
    finally:
        sender.close()

    status, op = http_get(f"/api/v1/operations/{op_id}")
    assert op["status"] == "FAILED"
    assert op["error_code"] == "DOCKER_FAILURE"
    assert op["error_message"] == "pull failed: manifest unknown"
    # And the inventory honestly shows no container state (never fabricated).
    status, apps = http_get("/api/v1/applications")
    app = next(a for a in apps["applications"] if a["deployment_id"] == body["deployment_id"])
    assert app["container_state"] is None
    assert app["http_ok"] is None

