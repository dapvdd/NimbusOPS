"""HTTP client for the control server with bounded retry/backoff.

All failures are explicit: senders return (ok, detail) instead of hiding
errors. Transient network errors are retried with exponential backoff and
jitter, up to max_retries per send. Authentication failures (401/403) are
NOT retried — they need operator action.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("nimbusops.agent")

RETRYABLE_STATUS = {500, 502, 503, 504}


class AuthError(RuntimeError):
    """Server rejected our credentials. Not retried automatically."""


class Sender:
    def __init__(
        self,
        server_url: str,
        host_id: str,
        agent_token: str,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        backoff_initial: float = 1.0,
        backoff_max: float = 30.0,
        retry_status: set[int] | None = None,
        sleep_fn=time.sleep,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.host_id = host_id
        self.agent_token = agent_token
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_initial = backoff_initial
        self.backoff_max = backoff_max
        self.retry_status = retry_status or RETRYABLE_STATUS
        self._sleep = sleep_fn
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> dict:
        return {"X-Host-Id": self.host_id, "Authorization": f"Bearer {self.agent_token}"}

    def _post(self, path: str, payload: dict[str, Any]) -> tuple[bool, str]:
        """POST with bounded exponential backoff on transient failures."""
        url = f"{self.server_url}{path}"
        delay = self.backoff_initial
        last_detail = "unknown error"
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._client.post(url, json=payload, headers=self._headers())
            except httpx.HTTPError as exc:
                last_detail = f"network error: {type(exc).__name__}"
                logger.warning("POST %s failed (%s), attempt %d/%d", path, last_detail, attempt, self.max_retries)
            else:
                if 200 <= resp.status_code < 300:
                    return True, "ok"
                if resp.status_code in (401, 403):
                    raise AuthError(f"server rejected credentials (HTTP {resp.status_code})")
                if resp.status_code in self.retry_status:
                    last_detail = f"server error HTTP {resp.status_code}"
                    logger.warning("POST %s got %s, attempt %d/%d", path, resp.status_code, attempt, self.max_retries)
                else:
                    return False, f"server rejected payload: HTTP {resp.status_code}: {resp.text[:200]}"
            if attempt < self.max_retries:
                jitter = random.uniform(0, delay * 0.3)
                self._sleep(min(delay + jitter, self.backoff_max))
                delay = min(delay * self.backoff_base, self.backoff_max)
        return False, f"giving up after {self.max_retries} attempts: {last_detail}"

    def enroll(self, hostname: str, enrollment_token: str, info: dict) -> tuple[bool, dict | str]:
        payload = {"hostname": hostname, "enrollment_token": enrollment_token, **info}
        try:
            resp = self._client.post(f"{self.server_url}/api/v1/agents/enroll", json=payload)
        except httpx.HTTPError as exc:
            return False, f"network error: {type(exc).__name__}: {exc}"
        if 200 <= resp.status_code < 300:
            body = resp.json()
            return True, {"host_id": body["host_id"], "agent_token": body["agent_token"]}
        detail = f"HTTP {resp.status_code}: {resp.text[:200]}"
        if resp.status_code in (401, 403):
            raise AuthError(detail)
        return False, detail

    def send_heartbeat(self, info: dict) -> tuple[bool, str]:
        payload: dict[str, Any] = {}
        for key, value in info.items():
            if isinstance(value, datetime):
                payload[key] = value.astimezone(timezone.utc).isoformat()
            else:
                payload[key] = value
        return self._post("/api/v1/agents/heartbeat", payload)

    def send_telemetry(self, telemetry: dict) -> tuple[bool, str]:
        payload: dict[str, Any] = {}
        for key, value in telemetry.items():
            if key.startswith("_"):
                continue
            if isinstance(value, datetime):
                payload[key] = value.astimezone(timezone.utc).isoformat()
            else:
                payload[key] = value
        return self._post("/api/v1/agents/telemetry", payload)

    # ---------------------------------------------------------------- Phase 2

    def poll_commands(self) -> dict:
        """Fetch (and thereby claim) queued operations for this host."""
        try:
            resp = self._client.post(
                f"{self.server_url}/api/v1/agents/commands/poll", json={}, headers=self._headers()
            )
        except httpx.HTTPError as exc:
            raise ConnectionError(f"poll network error: {type(exc).__name__}: {exc}") from exc
        if resp.status_code in (401, 403):
            raise AuthError(f"server rejected credentials (HTTP {resp.status_code})")
        if resp.status_code >= 400:
            raise ConnectionError(f"poll failed: HTTP {resp.status_code}")
        return resp.json()

    def submit_command_result(self, operation_id: str, payload: dict) -> tuple[bool, str]:
        """Report one operation outcome (idempotent server-side)."""
        try:
            resp = self._client.post(
                f"{self.server_url}/api/v1/agents/commands/{operation_id}/result",
                json=payload,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            return False, f"network error: {type(exc).__name__}"
        if 200 <= resp.status_code < 300:
            return True, "ok"
        if resp.status_code in (401, 403):
            raise AuthError(f"server rejected credentials (HTTP {resp.status_code})")
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
