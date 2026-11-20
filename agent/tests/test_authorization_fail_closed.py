"""Docker dispatch authorization must reach the worker and fail closed.

The server's heartbeat response carries the authoritative ``docker_enabled``
flag. It is stored on ``Sender``; the worker must see it through the adapter.
A missing/unknown flag is treated as disabled — never as permission to run.
"""

from __future__ import annotations

from agent.nimbusops_agent.worker import (
    CommandWorker,
    SenderCommandAdapter,
    WorkerOutcome,
)

COMMAND = {
    "id": "op-auth-1",
    "deployment_id": "dep-1",
    "host_id": "host-1",
    "op_type": "RESTART",
    "claim_generation": 1,
    "template": {
        "key": "nginx-demo",
        "image": "nginx:1.27-alpine",
        "container_port": 80,
        "host_port": 18080,
        "container_name": "nimbusops-nginx-demo-abc12345",
    },
}


class FakeSender:
    """Minimal Sender shape: poll/result plus the heartbeat-derived flag."""

    def __init__(self, *, docker_enabled=True, expose_flag=True):
        self.result_calls: list[tuple[str, dict]] = []
        self.poll_calls = 0
        if expose_flag:
            self.docker_enabled = docker_enabled

    def poll_commands(self) -> dict:
        self.poll_calls += 1
        return {"commands": [dict(COMMAND)] if self.poll_calls == 1 else []}

    def submit_command_result(self, operation_id, payload):
        self.result_calls.append((operation_id, payload))
        return True, "ok"


class NoopExecutor:
    def __init__(self):
        self.executed: list[str] = []

    def execute(self, command):
        self.executed.append(command["id"])
        return {"status": "SUCCEEDED", "result": {"container_state": "RUNNING"}}


def _worker(sender):
    ex = NoopExecutor()
    worker = CommandWorker(http=SenderCommandAdapter(sender), executor=ex, sleep_fn=lambda _: None)
    return worker, ex


def test_adapter_exposes_sender_docker_enabled():
    adapter = SenderCommandAdapter(FakeSender(docker_enabled=False))
    assert adapter.docker_enabled is False


def test_adapter_fails_closed_when_sender_has_no_flag():
    adapter = SenderCommandAdapter(FakeSender(expose_flag=False))
    assert adapter.docker_enabled is None


def test_worker_never_executes_when_adapter_reports_disabled():
    sender = FakeSender(docker_enabled=False)
    worker, ex = _worker(sender)
    worker.poll_once()
    assert ex.executed == []
    assert worker.poll_once() == WorkerOutcome.IDLE
    payload = sender.result_calls[0][1]
    assert payload["status"] == "UNKNOWN"
    assert payload["error_code"] == "DOCKER_DISABLED"


def test_worker_fails_closed_when_authorization_flag_is_missing():
    sender = FakeSender(expose_flag=False)
    worker, ex = _worker(sender)
    worker.poll_once()
    assert ex.executed == []
    assert sender.result_calls[0][1]["error_code"] == "DOCKER_DISABLED"


def test_worker_fails_closed_when_authorization_flag_is_unknown():
    sender = FakeSender(docker_enabled=None)
    worker, ex = _worker(sender)
    worker.poll_once()
    assert ex.executed == []
    assert sender.result_calls[0][1]["error_code"] == "DOCKER_DISABLED"


def test_worker_executes_with_explicit_true_authorization():
    sender = FakeSender(docker_enabled=True)
    worker, ex = _worker(sender)
    worker.poll_once()
    assert ex.executed == ["op-auth-1"]
    assert sender.result_calls[0][1]["status"] == "SUCCEEDED"
