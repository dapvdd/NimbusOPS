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
from .tls import custom_ca_context

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
        ca_bundle: str | None = None,
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
        self._client = (
            httpx.Client(timeout=timeout, verify=custom_ca_context(ca_bundle))
            if ca_bundle is not None
            else httpx.Client(timeout=timeout)
        )
        # RC2 F04: authoritative dispatch flag from the last heartbeat.
        # None means "not yet told"; callers should treat that conservatively.
        self.docker_enabled: bool | None = None

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> dict:
        return {"X-Host-Id": self.host_id, "Authorization": f"Bearer {self.agent_token}"}

    def _post(self, path: str, payload: dict[str, Any]) -> tuple[bool, str]:
        """POST with bounded exponential backoff on transient failures."""
        ok, detail, _body = self._post_json(path, payload)
        return ok, detail

    def _post_json(
        self, path: str, payload: dict[str, Any]
    ) -> tuple[bool, str, Any]:
        """POST and return (ok, detail, parsed_body_or_None)."""
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
                    try:
                        return True, "ok", resp.json()
                    except ValueError:
                        return True, "ok", None
                if resp.status_code in (401, 403):
                    raise AuthError(f"server rejected credentials (HTTP {resp.status_code})")
                if resp.status_code in self.retry_status:
                    last_detail = f"server error HTTP {resp.status_code}"
                    logger.warning("POST %s got %s, attempt %d/%d", path, resp.status_code, attempt, self.max_retries)
                else:
                    return False, f"server rejected payload: HTTP {resp.status_code}: {resp.text[:200]}", None
            if attempt < self.max_retries:
                jitter = random.uniform(0, delay * 0.3)
                self._sleep(min(delay + jitter, self.backoff_max))
                delay = min(delay * self.backoff_base, self.backoff_max)
        return False, f"giving up after {self.max_retries} attempts: {last_detail}", None

    def enroll(
        self,
        hostname: str,
        enrollment_token: str = "",
        info: dict | None = None,
        *,
        bootstrap_token: str | None = None,
    ) -> tuple[bool, dict | str]:
        """Enroll using exactly one credential.

        RC2 F01 canonical contract: a bootstrap token is sent as
        ``bootstrap_token``; the legacy shared secret is sent as
        ``enrollment_token``. Never both. Token material is never included in
        a returned error detail.
        """
        if bootstrap_token and enrollment_token:
            raise ValueError("provide exactly one of bootstrap_token or enrollment_token")
        if not bootstrap_token and not enrollment_token:
            raise ValueError("an enrollment credential is required")
        payload: dict[str, Any] = {"hostname": hostname, **(info or {})}
        if bootstrap_token:
            payload["bootstrap_token"] = bootstrap_token
        else:
            payload["enrollment_token"] = enrollment_token
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
        ok, detail, body = self._post_json("/api/v1/agents/heartbeat", payload)
        if ok and isinstance(body, dict) and isinstance(body.get("docker_enabled"), bool):
            self.docker_enabled = body["docker_enabled"]
        return ok, detail

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
