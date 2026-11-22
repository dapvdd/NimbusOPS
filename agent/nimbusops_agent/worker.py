"""Agent command worker: bounded polling, fail-closed dispatch, recoverable results.

Outbound-only: the agent POSTs /agents/commands/poll and
/agents/commands/{id}/result. No inbound ports.

Guarantees:
- Docker dispatch requires an explicit ``docker_enabled is True`` from the
  last heartbeat. Missing, unknown, or disabled all fail closed: no Docker
  mutation, and an honest UNKNOWN/DOCKER_DISABLED result is reported.
- Poll failures are transient: bounded retries with short delay; exceeding
  the bound returns TRANSIENT_ERROR (loop continues on next cycle).
- AuthError propagates (credentials need operator action, per Phase 1
  semantics: not retried, loop stops).
- An executed outcome is written to a durable store BEFORE delivery is
  attempted (write-ahead). A delivery failure leaves it pending; later
  cycles (and fresh processes) retry submission instead of re-executing.
- A redelivered operation with a pending outcome is reconciled by resubmitting
  the stored result with the newest claim generation, never by re-running
  Docker. Delivery uses bounded retries; the backend endpoint is idempotent.

Limits (stated honestly, not claimed as exactly-once):
- A crash between the executor returning and the write-ahead record being
  persisted can leave the operation requeued. The executor's ownership and
  CONTAINER_EXISTS guards then turn a second attempt into a typed failure;
  the original outcome cannot be reconstructed. This is at-least-once
  execution with best-effort outcome recovery, not exactly-once execution.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import tempfile
import time
from collections.abc import Callable
from enum import Enum
from typing import Any, Protocol, cast

JsonObject = dict[str, Any]

logger = logging.getLogger("nimbusops.agent.worker")


class WorkerOutcome(Enum):
    IDLE = "IDLE"
    EXECUTED = "EXECUTED"
    TRANSIENT_ERROR = "TRANSIENT_ERROR"


class CommandHttp(Protocol):
    def poll(self) -> JsonObject: ...

    def submit_result(
        self, operation_id: str, payload: JsonObject
    ) -> tuple[bool, str]: ...


class OutcomeStore(Protocol):
    """Durable journal of outcomes produced but not yet acknowledged."""

    def pending(self) -> dict[str, JsonObject]: ...

    def put(self, operation_id: str, result: JsonObject) -> None: ...

    def remove(self, operation_id: str) -> None: ...


class SenderCommandAdapter:
    """Adapts Sender (poll_commands/submit_command_result) to the worker protocol.

    The heartbeat's authoritative ``docker_enabled`` value lives on Sender.
    Exposing it here is what lets the worker apply its local fail-closed guard
    even when a command was claimed just before an operator disabled Docker.
    """

    def __init__(self, sender: Any) -> None:
        self._sender = sender

    @property
    def docker_enabled(self) -> bool | None:
        """None means the server has not told us yet: treat as disabled."""
        value = getattr(self._sender, "docker_enabled", None)
        return value if isinstance(value, bool) else None

    def poll(self) -> JsonObject:
        return cast(JsonObject, self._sender.poll_commands())

    def submit_result(self, operation_id: str, payload: JsonObject) -> tuple[bool, str]:
        return cast(
            tuple[bool, str], self._sender.submit_command_result(operation_id, payload)
        )


class InMemoryOutcomeStore:
    """Non-durable default for callers that do not supply a journal."""

    def __init__(self) -> None:
        self._data: dict[str, JsonObject] = {}

    def pending(self) -> dict[str, JsonObject]:
        return dict(self._data)

    def put(self, operation_id: str, result: JsonObject) -> None:
        self._data[operation_id] = result

    def remove(self, operation_id: str) -> None:
        self._data.pop(operation_id, None)


class FileOutcomeStore:
    """Atomic, owner-only JSON journal for pending operation outcomes.

    Uses temp-file + ``os.replace`` so a crash leaves either the previous
    valid journal or the new one — never a truncated document. The journal
    holds results/errors only, never credentials.
    """

    def __init__(self, path: pathlib.Path) -> None:
        self._path = pathlib.Path(path)
        self._data = self._load()

    def _load(self) -> dict[str, JsonObject]:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            raise RuntimeError("OUTCOME_JOURNAL_UNREADABLE") from None
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            raise RuntimeError("OUTCOME_JOURNAL_UNREADABLE") from None
        if not isinstance(data, dict):
            # A corrupt persisted journal is an operational failure, not a caller type error.
            raise RuntimeError("OUTCOME_JOURNAL_UNREADABLE")  # noqa: TRY004
        if any(
            not isinstance(value, dict) or "status" not in value
            for value in data.values()
        ):
            raise RuntimeError("OUTCOME_JOURNAL_UNREADABLE")
        return cast(dict[str, JsonObject], data)

    def _persist(self) -> None:
        payload = json.dumps(self._data, sort_keys=True)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".pending-", suffix=".tmp", dir=str(self._path.parent)
        )
        tmp = pathlib.Path(tmp_name)
        try:
            try:
                os.fchmod(fd, 0o600)
            except (AttributeError, OSError, NotImplementedError):
                pass
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self._path)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                tmp.unlink()
            except OSError:
                pass
            raise

    def pending(self) -> dict[str, JsonObject]:
        return dict(self._data)

    def put(self, operation_id: str, result: JsonObject) -> None:
        self._data[operation_id] = result
        self._persist()

    def remove(self, operation_id: str) -> None:
        if operation_id in self._data:
            del self._data[operation_id]
            self._persist()


class CommandWorker:
    def __init__(
        self,
        http: CommandHttp,
        executor: Any,
        poll_retry: int = 3,
        retry_delay: float = 1.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        outcome_store: OutcomeStore | None = None,
    ) -> None:
        self._http = http
        self._executor = executor
        self._poll_retry = poll_retry
        self._retry_delay = retry_delay
        self._sleep = sleep_fn
        self._store = outcome_store or InMemoryOutcomeStore()
        self._outcomes = self._store.pending()
        # Anything with a pending outcome must never be executed again.
        self._seen: set[str] = set(self._outcomes)

    def poll_once(self) -> WorkerOutcome:
        flushed = self._flush_pending()
        commands = self._poll_with_retry()
        if commands is None:
            return WorkerOutcome.TRANSIENT_ERROR
        executed_any = flushed
        for cmd in commands:
            op_id = str(cmd.get("id", ""))
            if not op_id:
                continue
            if op_id in self._seen:
                # Outcome produced by this or a previous process. Reconcile by
                # resubmitting it — never by running Docker a second time.
                if op_id in self._outcomes:
                    self._reconcile_redelivery(op_id, cmd)
                continue

            # Fail closed: no explicit authorization, no mutation.
            if getattr(self._http, "docker_enabled", None) is not True:
                payload = {
                    "status": "UNKNOWN",
                    "result": None,
                    "error_code": "DOCKER_DISABLED",
                    "error_message": (
                        "docker operations are disabled for this host; "
                        "operation was not executed"
                    ),
                }
            else:
                payload = self._executor.execute(cmd)

            result = self._build_result(cmd, payload)
            self._seen.add(op_id)
            # Write-ahead: survive a crash that happens during delivery.
            self._store.put(op_id, result)
            self._outcomes[op_id] = result
            if self._deliver(op_id, result):
                self._discard(op_id)
            executed_any = True
        return WorkerOutcome.EXECUTED if executed_any else WorkerOutcome.IDLE

    # ------------------------------------------------------------- internals

    def _poll_with_retry(self) -> list[JsonObject] | None:
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

    def _flush_pending(self) -> bool:
        """Try once per cycle to deliver each still-pending outcome."""
        delivered_any = False
        for op_id in list(self._outcomes):
            if self._deliver(op_id, self._outcomes[op_id]):
                self._discard(op_id)
                delivered_any = True
        return delivered_any

    def _reconcile_redelivery(self, op_id: str, cmd: JsonObject) -> None:
        """Resubmit the stored outcome using the newest claim generation."""
        result = dict(self._outcomes[op_id])
        generation = cmd.get("claim_generation")
        if generation is not None and result.get("claim_generation") != generation:
            result["claim_generation"] = generation
            self._outcomes[op_id] = result
            # Write-ahead again so a crash here cannot restore a stale claim.
            self._store.put(op_id, result)
        if self._deliver(op_id, result):
            self._discard(op_id)

    @staticmethod
    def _build_result(cmd: JsonObject, payload: JsonObject) -> JsonObject:
        result = {
            "status": payload.get("status", "UNKNOWN"),
            "result": payload.get("result"),
            "error_code": payload.get("error_code"),
            "error_message": payload.get("error_message"),
        }
        # RC2 F07: echo the claim generation so a delayed result from an
        # expired claim cannot win after the operation was re-delivered.
        if cmd.get("claim_generation") is not None:
            result["claim_generation"] = cmd["claim_generation"]
        return result

    def _deliver(self, op_id: str, result: JsonObject) -> bool:
        """Bounded, idempotent submission. True once the server acknowledges."""
        for attempt in range(1, self._poll_retry + 1):
            try:
                ok, detail = self._http.submit_result(op_id, result)
            except Exception as exc:
                if type(exc).__name__ == "AuthError":
                    raise
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            if ok:
                return True
            logger.warning(
                "result for op %s delivery failed (attempt %d/%d): %s",
                op_id,
                attempt,
                self._poll_retry,
                detail,
            )
            if attempt < self._poll_retry:
                self._sleep(self._retry_delay)
        logger.error(
            "result for op %s could not be delivered after %d attempts; "
            "kept in pending journal for a later cycle",
            op_id,
            self._poll_retry,
        )
        return False

    def _discard(self, op_id: str) -> None:
        self._store.remove(op_id)
        self._outcomes.pop(op_id, None)
