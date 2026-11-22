"""Real loopback backend/Sender recovery; Docker execution is synthetic, not Engine.

A new worker, Sender and file-store instance model agent object restart, not an
OS/process crash. The backend remains running against its disposable SQLite DB.
"""

from pathlib import Path
from typing import Any

import pytest

from agent.nimbusops_agent.worker import (
    CommandWorker,
    FileOutcomeStore,
    SenderCommandAdapter,
    WorkerOutcome,
)
from backend.tests_integration import test_phase2_flow as phase2
from backend.tests_integration.test_phase2_flow import (
    authorized_sender,
    deploy_request,
    enable_docker,
    http_get,
    http_post,
    operator_session,
)

# Reuse the established disposable DB and loopback-server fixtures.
server = phase2.server
identity = phase2.identity


class SyntheticDockerExecutor:
    """Record dispatch and return synthetic evidence; never invoke Docker."""

    def __init__(self) -> None:
        self.executed: list[dict[str, Any]] = []

    def execute(self, command: dict[str, Any]) -> dict[str, Any]:
        self.executed.append(command)
        return {
            "status": "SUCCEEDED",
            "result": {"container_state": "RUNNING", "http_ok": True},
        }


class LostResultAdapter(SenderCommandAdapter):
    """Inject transport loss before delivery or after real server acceptance."""

    def __init__(self, sender: Any, *, lose_ack: bool) -> None:
        super().__init__(sender)
        self.lose_ack = lose_ack
        self.attempts = 0

    def submit_result(
        self, operation_id: str, payload: dict[str, Any]
    ) -> tuple[bool, str]:
        self.attempts += 1
        if self.lose_ack:
            ok, detail = super().submit_result(operation_id, payload)
            assert ok, detail
        return False, "synthetic result transport loss"


@pytest.mark.parametrize("lose_ack", [False, True], ids=["lost-request", "lost-ack"])
def test_file_journal_restart_recovers_real_backend_result(
    server: Any,
    identity: tuple[str, str],
    tmp_path: Path,
    lose_ack: bool,
) -> None:
    """Recover pending evidence and deduplicate an accepted-but-unacked result."""
    host_id, token = identity
    headers = operator_session(server)
    enable_docker(server, host_id, headers)
    status, deployment = http_post(
        "/api/v1/applications/deploy", deploy_request(host_id), headers=headers
    )
    assert status == 202, deployment
    operation_id = deployment["operation_id"]
    journal = tmp_path / "pending-results.json"

    first_executor = SyntheticDockerExecutor()
    first_sender = authorized_sender(host_id, token)
    adapter = LostResultAdapter(first_sender, lose_ack=lose_ack)
    try:
        first_worker = CommandWorker(
            http=adapter,
            executor=first_executor,
            outcome_store=FileOutcomeStore(journal),
            sleep_fn=lambda _: None,
        )
        assert first_worker.poll_once() == WorkerOutcome.EXECUTED
    finally:
        first_sender.close()
    assert adapter.attempts == 3
    assert [cmd["id"] for cmd in first_executor.executed] == [operation_id]
    pending = FileOutcomeStore(journal).pending()
    assert pending[operation_id]["status"] == "SUCCEEDED"
    assert pending[operation_id]["claim_generation"] == 1
    status, before = http_get(f"/api/v1/operations/{operation_id}")
    assert status == 200
    assert before["status"] == ("SUCCEEDED" if lose_ack else "RUNNING")

    # New object graph, same durable journal and actual backend operation.
    second_executor = SyntheticDockerExecutor()
    second_sender = authorized_sender(host_id, token)
    try:
        second_worker = CommandWorker(
            http=SenderCommandAdapter(second_sender),
            executor=second_executor,
            outcome_store=FileOutcomeStore(journal),
            sleep_fn=lambda _: None,
        )
        assert second_worker.poll_once() == WorkerOutcome.EXECUTED
        assert second_worker.poll_once() == WorkerOutcome.IDLE
    finally:
        second_sender.close()
    assert second_executor.executed == []
    assert FileOutcomeStore(journal).pending() == {}
    status, after = http_get(f"/api/v1/operations/{operation_id}")
    assert status == 200
    assert after["status"] == "SUCCEEDED"
    assert after["result"] == pending[operation_id]["result"]
    if lose_ack:
        assert after["completed_at"] == before["completed_at"]
    status, inventory = http_get("/api/v1/applications")
    assert status == 200
    mine = [app for app in inventory["applications"] if app["host_id"] == host_id]
    assert len(mine) == 1
    assert mine[0]["deployment_id"] == deployment["deployment_id"]
    assert mine[0]["container_state"] == "RUNNING"
    assert mine[0]["http_ok"] is True
