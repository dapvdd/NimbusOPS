"""Agent command worker: bounded polling + authenticated result submission.

Outbound-only: the agent POSTs /agents/commands/poll and
/agents/commands/{id}/result. No inbound ports.

Guarantees:
- Executed op ids are remembered (in-memory per process) so duplicate
  deliveries are never re-executed.
- Poll failures are transient: bounded retries with short delay; exceeding
  the bound returns TRANSIENT_ERROR (loop continues on next cycle).
- AuthError propagates (credentials need operator action, per Phase 1
  semantics: not retried, loop stops).
- Results are submitted exactly once per execution; submission failures are
  retried with the SAME bounded policy (server is idempotent, so a retry
  cannot create duplicate effects).
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger("nimbusops.agent.worker")


class WorkerOutcome(Enum):
    IDLE = "IDLE"
    EXECUTED = "EXECUTED"
    TRANSIENT_ERROR = "TRANSIENT_ERROR"


class CommandHttp(Protocol):
    def poll(self) -> dict: ...

    def submit_result(self, operation_id: str, payload: dict) -> tuple[bool, str]: ...


class SenderCommandAdapter:
    """Adapts Sender (poll_commands/submit_command_result) to the worker protocol."""

    def __init__(self, sender: Any) -> None:
        self._sender = sender

    def poll(self) -> dict:
        return self._sender.poll_commands()

    def submit_result(self, operation_id: str, payload: dict) -> tuple[bool, str]:
        return self._sender.submit_command_result(operation_id, payload)


class CommandWorker:
    def __init__(
        self,
        http: CommandHttp,
        executor: Any,
        poll_retry: int = 3,
        retry_delay: float = 1.0,
        sleep_fn=time.sleep,
    ) -> None:
        self._http = http
        self._executor = executor
        self._poll_retry = poll_retry
        self._retry_delay = retry_delay
        self._sleep = sleep_fn
        self._seen: set[str] = set()  # op ids executed this process

    def poll_once(self) -> WorkerOutcome:
        commands = self._poll_with_retry()
        if commands is None:
            return WorkerOutcome.TRANSIENT_ERROR
        if not commands:
            return WorkerOutcome.IDLE

        executed_any = False
        for cmd in commands:
            op_id = str(cmd.get("id", ""))
            if not op_id or op_id in self._seen:
                continue  # duplicate delivery: never re-execute
            self._seen.add(op_id)
            self._execute_and_report(cmd)
            executed_any = True
        return WorkerOutcome.EXECUTED if executed_any else WorkerOutcome.IDLE

    # ------------------------------------------------------------- internals

    def _poll_with_retry(self) -> list[dict] | None:
        last_err: Exception | None = None
        for attempt in range(1, self._poll_retry + 1):
            try:
                body = self._http.poll()
                return list(body.get("commands") or [])
            except Exception as exc:
                if type(exc).__name__ == "AuthError":
                    raise
                last_err = exc
                logger.warning(
                    "poll failed (attempt %d/%d): %s", attempt, self._poll_retry, exc
                )
                if attempt < self._poll_retry:
                    self._sleep(self._retry_delay)
        logger.error("poll giving up after %d attempts: %s", self._poll_retry, last_err)
        return None

    def _execute_and_report(self, cmd: dict) -> None:
        op_id = str(cmd.get("id", ""))
        payload = self._executor.execute(cmd)
        result = {
            "status": payload.get("status", "UNKNOWN"),
            "result": payload.get("result"),
            "error_code": payload.get("error_code"),
            "error_message": payload.get("error_message"),
        }
        ok, detail = self._http.submit_result(op_id, result)
        if not ok:
            # Bounded retry for result submission; server is idempotent so a
            # retry never duplicates effects.
            for attempt in range(2, self._poll_retry + 1):
                self._sleep(self._retry_delay)
                ok, detail = self._http.submit_result(op_id, result)
                if ok:
                    break
            if not ok:
                logger.error(
                    "result for op %s could not be delivered after %d attempts: %s",
                    op_id, self._poll_retry, detail,
                )
