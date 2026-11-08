"""Phase 2 agent tests: command polling loop (MOCKED HTTP + MOCKED Docker).

Covers: claim handling, result submission, duplicate delivery, bounded
retries, reconnection after disconnect, unknown command handling.
"""

import pytest

from agent.nimbusops_agent.worker import CommandWorker, WorkerOutcome


class FakeHttp:
    """Scripted HTTP for poll/result; records calls."""

    def __init__(self, polls=None, results=None):
        self.poll_responses = list(polls or [])
        self.result_responses = list(results or [])
        self.poll_calls = 0
        self.result_calls = []
        self.fail_next_polls = 0

    def poll(self) -> dict:
        self.poll_calls += 1
        if self.fail_next_polls > 0:
            self.fail_next_polls -= 1
            raise ConnectionError("simulated network failure")
        if self.poll_responses:
            return self.poll_responses.pop(0)
        return {"commands": []}

    def submit_result(self, operation_id: str, payload: dict) -> tuple[bool, str]:
        self.result_calls.append((operation_id, payload))
        if self.result_responses:
            return self.result_responses.pop(0)
        return True, "ok"


NGINX = {
    "key": "nginx-demo",
    "image": "nginx:1.27-alpine",
    "container_port": 80,
    "host_port": 8080,
    "container_name": "nimbusops-nginx-demo-abc12345",
}


def make_command(op_id="op-1", op_type="DEPLOY", deployment_id="dep-1"):
    return {
        "id": op_id,
        "deployment_id": deployment_id,
        "host_id": "host-1",
        "op_type": op_type,
        "status": "RUNNING",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "completed_at": None,
        "result": None,
        "error_code": None,
        "error_message": None,
        "template": dict(NGINX),
    }


class NoopExecutor:
    def __init__(self, outcome=None):
        self.outcome = outcome or {"status": "SUCCEEDED", "result": {"container_state": "RUNNING", "http_ok": True}}
        self.executed = []

    def execute(self, command):
        self.executed.append(command["id"])
        return dict(self.outcome)


# ------------------------------------------------------------- basic handling


def test_worker_executes_command_and_submits_result():
    http = FakeHttp(polls=[{"commands": [make_command()]}])
    ex = NoopExecutor()
    w = CommandWorker(http=http, executor=ex)
    outcome = w.poll_once()
    assert outcome == WorkerOutcome.EXECUTED
    assert ex.executed == ["op-1"]
    assert len(http.result_calls) == 1
    assert http.result_calls[0][0] == "op-1"
    assert http.result_calls[0][1]["status"] == "SUCCEEDED"


def test_worker_idle_when_no_commands():
    http = FakeHttp()
    w = CommandWorker(http=http, executor=NoopExecutor())
    assert w.poll_once() == WorkerOutcome.IDLE


def test_worker_reports_failed_result():
    http = FakeHttp(polls=[{"commands": [make_command()]}])
    ex = NoopExecutor(outcome={"status": "FAILED", "error_code": "DOCKER_FAILURE", "error_message": "pull failed"})
    w = CommandWorker(http=http, executor=ex)
    w.poll_once()
    assert http.result_calls[0][1]["status"] == "FAILED"
    assert http.result_calls[0][1]["error_code"] == "DOCKER_FAILURE"


def test_worker_reports_unknown_result():
    http = FakeHttp(polls=[{"commands": [make_command()]}])
    ex = NoopExecutor(outcome={"status": "UNKNOWN", "error_code": "TIMEOUT", "error_message": "timed out"})
    w = CommandWorker(http=http, executor=ex)
    w.poll_once()
    payload = http.result_calls[0][1]
    assert payload["status"] == "UNKNOWN"
    assert payload["error_code"] == "TIMEOUT"


# --------------------------------------------------- duplicate / disconnect


def test_duplicate_command_delivery_executes_once():
    """Poller re-delivering the same op id (e.g., claim raced) must not
    execute twice: worker remembers completed op ids within its lifetime."""
    http = FakeHttp(
        polls=[
            {"commands": [make_command()]},
            {"commands": [make_command()]},  # duplicate delivery
        ]
    )
    ex = NoopExecutor()
    w = CommandWorker(http=http, executor=ex)
    w.poll_once()
    w.poll_once()
    assert ex.executed == ["op-1"], "duplicate delivery must not re-execute"
    # Second submission attempt: server-side idempotency means ack says not accepted.
    assert len(http.result_calls) == 1


def test_disconnect_during_poll_is_bounded_and_recovers():
    http = FakeHttp(
        polls=[{"commands": [make_command()]}],
    )
    http.fail_next_polls = 2  # fail twice, then deliver
    ex = NoopExecutor()
    w = CommandWorker(http=http, executor=ex, poll_retry=3)
    outcome = w.poll_once()
    assert outcome == WorkerOutcome.EXECUTED
    assert http.poll_calls == 3


def test_disconnect_exceeding_bounded_retries_reports_error():
    http = FakeHttp()
    http.fail_next_polls = 10
    ex = NoopExecutor()
    w = CommandWorker(http=http, executor=ex, poll_retry=3)
    outcome = w.poll_once()
    assert outcome == WorkerOutcome.TRANSIENT_ERROR


def test_reconnection_does_not_lose_operations():
    """Ops claimed but never executed (process restart) are re-claimed by the
    backend when the agent reconnects — backend flips RUNNING back to QUEUED
    after a claim timeout. Here: worker restart forgets executed set; backend
    re-delivers; worker executes the fresh delivery."""
    http = FakeHttp(polls=[{"commands": [make_command()]}])
    ex = NoopExecutor()
    w1 = CommandWorker(http=http, executor=ex)
    # Simulate: op claimed, worker crashed before executing.
    w1._seen.clear()
    w2 = CommandWorker(http=http, executor=ex)  # fresh worker (restart)
    outcome = w2.poll_once()
    assert outcome == WorkerOutcome.EXECUTED


def test_auth_error_stops_worker():
    from agent.nimbusops_agent.client import AuthError

    class AuthFailHttp:
        def poll(self):
            raise AuthError("rejected")

        def submit_result(self, *a, **k):
            return True, "ok"

    w = CommandWorker(http=AuthFailHttp(), executor=NoopExecutor())
    with pytest.raises(AuthError):
        w.poll_once()


def test_invalid_command_payload_does_not_crash_worker():
    from agent.nimbusops_agent.docker_exec import DockerExecutor

    http = FakeHttp(polls=[{"commands": [{"id": "op-x"}]}])  # no op_type/template
    ex = DockerExecutor(runner=lambda a, t: (0, "", ""))  # never called
    w = CommandWorker(http=http, executor=ex)
    outcome = w.poll_once()
    # Executor rejects it; worker submits the failure and continues.
    assert outcome == WorkerOutcome.EXECUTED
    assert http.result_calls[0][1]["status"] == "FAILED"
    assert http.result_calls[0][1]["error_code"] == "UNAPPROVED_OPERATION"
