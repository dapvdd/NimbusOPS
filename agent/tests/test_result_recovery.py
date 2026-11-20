"""Operation-result recovery: no silently lost outcomes, no duplicate execution.

The agent writes the outcome to a durable store *before* attempting delivery.
If delivery fails, the outcome is retried on later cycles and after a process
restart. A redelivered operation resubmits its stored outcome with the fresh
claim generation instead of running Docker a second time.

Docker side effects are NOT claimed to be exactly-once: a crash between the
executor returning and the write-ahead record can still requeue the operation.
"""

from __future__ import annotations

from agent.nimbusops_agent.worker import CommandWorker, FileOutcomeStore

COMMAND = {
    "id": "op-recovery-1",
    "deployment_id": "dep-1",
    "host_id": "host-1",
    "op_type": "DEPLOY",
    "claim_generation": 1,
    "template": {
        "key": "nginx-demo",
        "image": "nginx:1.27-alpine",
        "container_port": 80,
        "host_port": 18080,
        "container_name": "nimbusops-nginx-demo-abc12345",
    },
}


class FakeHttp:
    def __init__(self, polls=None, results=None):
        self.polls = list(polls or [])
        self.results = list(results or [])
        self.result_calls: list[tuple[str, dict]] = []
        self.docker_enabled = True

    def poll(self) -> dict:
        return self.polls.pop(0) if self.polls else {"commands": []}

    def submit_result(self, operation_id, payload):
        self.result_calls.append((operation_id, payload))
        return self.results.pop(0) if self.results else (True, "ok")


class NoopExecutor:
    def __init__(self):
        self.executed: list[str] = []

    def execute(self, command):
        self.executed.append(command["id"])
        return {"status": "SUCCEEDED", "result": {"container_state": "RUNNING", "http_ok": True}}


class InMemoryOutcomeStore:
    """Test double shared across workers to emulate a durable store."""

    def __init__(self):
        self._data: dict[str, dict] = {}

    def pending(self) -> dict[str, dict]:
        return dict(self._data)

    def put(self, operation_id, result):
        self._data[operation_id] = result

    def remove(self, operation_id):
        self._data.pop(operation_id, None)


def _worker(http, executor, store):
    return CommandWorker(
        http=http, executor=executor, outcome_store=store,
        poll_retry=3, sleep_fn=lambda _: None,
    )


def test_failed_result_delivery_is_persisted_and_retried():
    store = InMemoryOutcomeStore()
    http = FakeHttp(
        polls=[{"commands": [dict(COMMAND)]}],
        results=[(False, "network loss")] * 3,
    )
    ex = NoopExecutor()
    worker = _worker(http, ex, store)

    worker.poll_once()

    assert ex.executed == ["op-recovery-1"], "execute exactly once"
    assert len(http.result_calls) == 3
    assert "op-recovery-1" in store.pending(), "undelivered outcome must be durable"

    http.results = [(True, "ok")]
    worker.poll_once()

    assert len(http.result_calls) == 4
    assert "op-recovery-1" not in store.pending(), "delivered outcome must be cleared"
    assert http.result_calls[-1][1]["status"] == "SUCCEEDED"


def test_redelivered_operation_resubmits_stored_result_without_reexecuting():
    store = InMemoryOutcomeStore()
    redelivered = dict(COMMAND, claim_generation=2)
    http = FakeHttp(
        polls=[{"commands": [dict(COMMAND)]}, {"commands": [redelivered]}],
        # 3 attempts for the initial delivery, 3 for the cycle-start flush,
        # then the redelivery reconciliation succeeds.
        results=[(False, "loss")] * 6 + [(True, "ok")],
    )
    ex = NoopExecutor()
    worker = _worker(http, ex, store)

    worker.poll_once()  # execute + 3 failed submissions
    worker.poll_once()  # flush retry fails, then redelivery refreshes generation

    assert ex.executed == ["op-recovery-1"], "redelivery must not re-run Docker"
    assert http.result_calls[-1][0] == "op-recovery-1"
    assert http.result_calls[-1][1]["claim_generation"] == 2
    assert "op-recovery-1" not in store.pending()


def test_worker_restart_recovers_pending_outcome_without_reexecuting():
    store = InMemoryOutcomeStore()
    http1 = FakeHttp(polls=[{"commands": [dict(COMMAND)]}], results=[(False, "loss")] * 3)
    ex1 = NoopExecutor()
    _worker(http1, ex1, store).poll_once()
    assert "op-recovery-1" in store.pending()

    # Fresh process: new worker/http/executor, same durable store.
    http2 = FakeHttp()
    ex2 = NoopExecutor()
    worker2 = _worker(http2, ex2, store)
    worker2.poll_once()

    assert ex2.executed == [], "restart must resubmit, never re-execute"
    assert len(http2.result_calls) == 1
    assert http2.result_calls[0][1]["status"] == "SUCCEEDED"
    assert "op-recovery-1" not in store.pending()


def test_pending_outcome_is_written_before_delivery_is_attempted():
    store = InMemoryOutcomeStore()
    seen_at_submit: list[bool] = []

    class CheckHttp(FakeHttp):
        def submit_result(self, operation_id, payload):
            seen_at_submit.append(operation_id in store.pending())
            return super().submit_result(operation_id, payload)

    http = CheckHttp(polls=[{"commands": [dict(COMMAND)]}])
    _worker(http, NoopExecutor(), store).poll_once()

    assert seen_at_submit and all(seen_at_submit), "write-ahead record missing at submit time"


def test_file_outcome_store_survives_new_instance(tmp_path):
    path = tmp_path / "pending_results.json"

    first = FileOutcomeStore(path)
    first.put("op-file-1", {"status": "SUCCEEDED", "claim_generation": 4})

    second = FileOutcomeStore(path)
    assert second.pending()["op-file-1"]["status"] == "SUCCEEDED"

    second.remove("op-file-1")
    assert FileOutcomeStore(path).pending() == {}
