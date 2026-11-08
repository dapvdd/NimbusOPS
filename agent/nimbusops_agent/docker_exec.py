"""Agent-side Docker execution: constrained, label-scoped, evidence-first.

Safety model (brief §6):
- Docker is OPTIONAL: every public method returns a typed outcome; the
  telemetry loop is unaffected when Docker is unavailable.
- Only the docker CLI is invoked, as fixed argv lists (no shell, no string
  interpolation into a shell). No docker SDK dependency.
- Only NimbusOps-managed resources are touched: container names MUST start
  with the "nimbusops-" prefix, and containers are created with labels
  nimbusops.managed=true and nimbusops.deployment=<id>.
- No privileged mode, no host mounts, no prune, no volume/network removal,
  no arbitrary image (template must be approved upstream; the agent
  double-checks the image allowlist too).
- Never reports SUCCEEDED without verification evidence: after run/start,
  `docker ps` must show the container up; an HTTP probe on the mapped port
  adds availability evidence. Unverifiable/timeout -> UNKNOWN.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any, Callable

import httpx

logger = logging.getLogger("nimbusops.agent.docker")

MANAGED_PREFIX = "nimbusops-"
LABEL_MANAGED = "nimbusops.managed=true"
LABEL_DEPLOYMENT = "nimbusops.deployment"

# Approved images the agent will run, double-checking upstream approval.
APPROVED_IMAGES = {"nginx:1.27-alpine"}

DEFAULT_TIMEOUT = 120.0


class DockerUnavailable(RuntimeError):
    """Docker CLI/daemon not usable; monitoring continues without Docker."""


class ManagedResourceError(RuntimeError):
    """Attempt to touch a resource outside the NimbusOps-managed scope."""


class VerifyFailed(RuntimeError):
    """Outcome could not be verified (container not up / probe failed)."""


def parse_container_state(ps_line: str) -> str | None:
    """Map `docker ps --format {{.Status}}` text to a state word."""
    line = (ps_line or "").strip()
    if not line:
        return None
    lowered = line.lower()
    if lowered.startswith("up"):
        return "RUNNING"
    if "paused" in lowered:
        return "PAUSED"
    if lowered.startswith("created"):
        return "CREATED"
    if lowered.startswith("exited"):
        return "EXITED"
    if lowered.startswith("dead"):
        return "DEAD"
    return "UNKNOWN"


class DockerExecutor:
    """Executes approved deployment operations against the local Docker Engine.

    `runner` is injectable for tests: callable(argv: list[str], timeout: float)
    -> (returncode, stdout, stderr). In production it is subprocess.run-based.
    """

    def __init__(
        self,
        runner: Callable[[list[str], float], tuple[int, str, str]] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._runner = runner or self._subprocess_runner
        self._timeout = timeout
        self._available: bool | None = None

    # ------------------------------------------------------------- plumbing

    @staticmethod
    def _subprocess_runner(argv: list[str], timeout: float) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                check=False,
            )
        except FileNotFoundError as exc:
            return 127, "", f"docker CLI not found: {exc}"
        return proc.returncode, proc.stdout, proc.stderr

    def _run(self, argv: list[str], timeout: float | None = None) -> tuple[int, str, str]:
        try:
            return self._runner(argv, timeout if timeout is not None else self._timeout)
        except FileNotFoundError as exc:
            return 127, "", f"docker CLI not found: {exc}"

    def ensure_available(self) -> None:
        """Probe Docker CLI+daemon once per executor; raise DockerUnavailable."""
        if self._available:
            return
        code, out, err = self._run(
            ["docker", "version", "--format", "{{.Server.Version}}"], timeout=10.0
        )
        if code != 0:
            raise DockerUnavailable(f"docker version failed: code={code} {err.strip()[:200]}")
        if not out.strip():
            raise DockerUnavailable("docker version returned no server version")
        self._available = True

    # ------------------------------------------------------------- ops

    def execute(self, command: dict[str, Any]) -> dict[str, Any]:
        """Dispatch one approved operation. Returns a result dict:
        {status: SUCCEEDED|FAILED|UNKNOWN, result?, error_code?, error_message?}
        """
        op_type = command.get("op_type")
        deployment_id = str(command.get("deployment_id", ""))
        template = command.get("template") or {}
        try:
            if op_type == "DEPLOY":
                return self._deploy(template, deployment_id)
            if op_type == "START":
                return self._start(template.get("container_name", ""), deployment_id, template.get("host_port"))
            if op_type == "STOP":
                return self._stop(template.get("container_name", ""), deployment_id)
            raise ManagedResourceError(f"op_type {op_type!r} is not approved")
        except DockerUnavailable as exc:
            return {
                "status": "FAILED",
                "error_code": "DOCKER_UNAVAILABLE",
                "error_message": str(exc)[:512],
            }
        except ManagedResourceError as exc:
            return {
                "status": "FAILED",
                "error_code": "UNAPPROVED_OPERATION",
                "error_message": str(exc)[:512],
            }
        except TimeoutError as exc:
            return {
                "status": "UNKNOWN",
                "error_code": "TIMEOUT",
                "error_message": str(exc)[:512] or "docker command timed out",
            }
        except Exception as exc:  # unexpected: never crash the loop
            return {
                "status": "UNKNOWN",
                "error_code": "UNKNOWN",
                "error_message": f"{type(exc).__name__}: {exc}"[:512],
        }

    # ------------------------------------------------------------ deploy

    def _deploy(self, template: dict[str, Any], deployment_id: str) -> dict[str, Any]:
        key = template.get("key", "")
        image = template.get("image", "")
        name = template.get("container_name", "")
        if key != "nginx-demo" or image not in APPROVED_IMAGES:
            raise ManagedResourceError(f"template {key!r} / image {image!r} not approved")
        if not name.startswith(MANAGED_PREFIX):
            raise ManagedResourceError(f"container name {name!r} outside managed prefix")

        # Validation first: unapproved scope never touches Docker at all.
        self.ensure_available()
        host_port = int(template.get("host_port", 8080))

        # 1. Pull (explicit image tag; bounded output).
        code, _, err = self._run(["docker", "pull", image])
        if code != 0:
            return {
                "status": "FAILED",
                "error_code": "DOCKER_FAILURE",
                "error_message": f"pull failed: {err.strip()[:300]}",
            }

        # 2. Run: detached, deterministic name, labels, published port,
        #    NO privileged, NO volumes/mounts, NO extra capabilities.
        run_argv = [
            "docker", "run", "-d",
            "--name", name,
            "--label", LABEL_MANAGED,
            "--label", f"{LABEL_DEPLOYMENT}={deployment_id}",
            "--restart", "no",
            "-p", f"{host_port}:{int(template.get('container_port', 80))}",
            image,
        ]
        code, _, err = self._run(run_argv)
        if code != 0:
            msg = err.strip()[:300]
            if "port is already allocated" in msg or "address already in use" in msg:
                return {
                    "status": "FAILED",
                    "error_code": "PORT_CONFLICT",
                    "error_message": f"host port {host_port} unavailable: {msg}",
                }
            return {
                "status": "FAILED",
                "error_code": "DOCKER_FAILURE",
                "error_message": f"run failed: {msg}",
            }

        # 3. Verify the container is actually running (evidence, not trust).
        return self._verify_running(name, deployment_id, host_port)

    def _verify_running(self, name: str, deployment_id: str, host_port: int | None) -> dict[str, Any]:
        code, out, _ = self._run(
            ["docker", "ps", "--filter", f"name=^{name}$", "--format", "{{.Status}}"]
        )
        if code != 0:
            return {
                "status": "UNKNOWN",
                "error_code": "VERIFY_FAILED",
                "error_message": f"docker ps failed: code={code}",
            }
        state = parse_container_state(out)
        if state != "RUNNING":
            return {
                "status": "UNKNOWN",
                "error_code": "VERIFY_FAILED",
                "error_message": f"container not running after deploy (state={state!r})",
            }
        http_ok = self.probe_http(host_port) if host_port else None
        return {
            "status": "SUCCEEDED",
            "result": {
                "container_id": name,
                "container_state": state,
                "http_ok": http_ok,
                **({"app_url": f"http://localhost:{host_port}/"} if host_port else {}),
            },
        }

    # ------------------------------------------------------- start / stop

    def deploy(self, template: dict[str, Any], deployment_id: str) -> dict[str, Any]:
        """Public wrapper: run the approved DEPLOY operation."""
        return self._deploy(template, deployment_id)

    def start(self, name: str, deployment_id: str, host_port: int | None = None) -> dict[str, Any]:
        """Public wrapper: start a managed container and verify."""
        return self._start(name, deployment_id, host_port)

    def stop(self, name: str, deployment_id: str) -> dict[str, Any]:
        """Public wrapper: stop a managed container and verify."""
        return self._stop(name, deployment_id)

    def _start(self, name: str, deployment_id: str, host_port: int | None = None) -> dict[str, Any]:
        if not name.startswith(MANAGED_PREFIX):
            raise ManagedResourceError(f"container name {name!r} outside managed prefix")
        self.ensure_available()
        code, _, err = self._run(["docker", "start", name])
        if code != 0:
            return {
                "status": "FAILED",
                "error_code": "DOCKER_FAILURE",
                "error_message": f"start failed: {err.strip()[:300]}",
            }
        return self._verify_running(name, deployment_id, host_port)

    def _stop(self, name: str, deployment_id: str) -> dict[str, Any]:
        if not name.startswith(MANAGED_PREFIX):
            raise ManagedResourceError(f"container name {name!r} outside managed prefix")
        self.ensure_available()
        code, _, err = self._run(["docker", "stop", name])
        if code != 0:
            return {
                "status": "FAILED",
                "error_code": "DOCKER_FAILURE",
                "error_message": f"stop failed: {err.strip()[:300]}",
            }
        code, out, _ = self._run(
            ["docker", "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Status}}"]
        )
        state = parse_container_state(out) if code == 0 else None
        if state not in ("EXITED", None):
            return {
                "status": "UNKNOWN",
                "error_code": "VERIFY_FAILED",
                "error_message": f"container did not confirm stopped (state={state!r})",
            }
        return {
            "status": "SUCCEEDED",
            "result": {"container_state": state or "EXITED", "http_ok": None},
        }

    # ------------------------------------------------------------ probe

    def probe_http(self, port: int, timeout: float = 5.0) -> bool:
        """HTTP availability probe; False on any failure (never raises)."""
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(f"http://127.0.0.1:{port}/")
                return 200 <= resp.status_code < 400
        except Exception:
            return False
