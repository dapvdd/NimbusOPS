"""Agent configuration with validation.

Identity is stable: on first run the agent generates/persists host_id and
enrollment proceeds; afterwards the stored identity is reused. Identity
file is written with restrictive permissions (0600 on POSIX).
"""

from __future__ import annotations

import json
import os
import pathlib
import platform
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

import psutil

from . import __version__

DEFAULT_SERVER_URL = "http://127.0.0.1:8000"
DEFAULT_INTERVAL = 30.0
MIN_INTERVAL = 5.0
MAX_INTERVAL = 3600.0


class ConfigError(ValueError):
    """Raised when agent configuration is invalid; prevents startup."""


@dataclass
class Config:
    server_url: str
    enrollment_token: str
    # RC2 F01: explicit secure enrollment mode. Exactly one credential may be
    # supplied for a host with no stored identity. The bootstrap token is
    # normally supplied via env/file, never as a command-line argument.
    bootstrap_token: str = ""
    interval: float = DEFAULT_INTERVAL
    state_file: pathlib.Path = field(
        default_factory=lambda: pathlib.Path.home() / ".nimbusops" / "agent.json"
    )
    once: bool = False

    def __post_init__(self) -> None:
        if not self.server_url:
            raise ConfigError("server_url is required")
        if not self.server_url.startswith(("http://", "https://")):
            raise ConfigError(f"server_url must be http(s): {self.server_url!r}")
        if self.enrollment_token and self.bootstrap_token:
            raise ConfigError(
                "provide exactly one of enrollment_token or bootstrap_token"
            )
        # Enrollment credentials are only needed for *fresh* enrollment. A
        # re-running agent with a persisted identity must start without one.
        if not (self.enrollment_token or self.bootstrap_token):
            if not load_identity(pathlib.Path(self.state_file)):
                raise ConfigError(
                    "enrollment_token or bootstrap_token is required when no stored identity exists "
                    "(never hardcode a default)"
                )
        if not (MIN_INTERVAL <= self.interval <= MAX_INTERVAL):
            raise ConfigError(f"interval must be within [{MIN_INTERVAL}, {MAX_INTERVAL}] s")
        self.state_file = pathlib.Path(self.state_file)

    @property
    def enrollment_mode(self) -> str:
        """Explicit mode: 'bootstrap', 'legacy', or 'identity' (stored)."""
        if self.bootstrap_token:
            return "bootstrap"
        if self.enrollment_token:
            return "legacy"
        return "identity"


@dataclass
class Identity:
    host_id: str
    agent_token: str

    def to_json(self) -> str:
        return json.dumps({"host_id": self.host_id, "agent_token": self.agent_token}, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Identity":
        data = json.loads(text)
        if not isinstance(data, dict) or not data.get("host_id") or not data.get("agent_token"):
            raise ValueError("identity file is missing host_id or agent_token")
        return cls(host_id=data["host_id"], agent_token=data["agent_token"])


def _restrict_permissions(path: pathlib.Path) -> None:
    """Best-effort owner-only access for the identity file.

    POSIX: mode 0600. Windows: remove inherited ACEs and grant the current
    user only (explicit ACL handling; os.chmod does not express this).
    Failures are swallowed: identity usability must not depend on ACL tooling,
    and the caller has already restricted the temp file before writing.
    """
    if os.name == "nt":
        user = os.environ.get("USERNAME")
        if not user:
            return
        try:
            subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
                capture_output=True,
                timeout=10,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        return
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def save_identity(path: pathlib.Path, identity: Identity) -> None:
    """Atomically persist identity with owner-only permissions.

    RC2 F14: the bytes are written to a uniquely named temp file in the same
    directory (created 0600 on POSIX before any write), fsync'd, then replaced
    over the target. A crash or write failure therefore leaves either the old
    valid identity or the new one — never a truncated file. On Windows the ACL
    is restricted explicitly after the replace.
    """
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = identity.to_json().encode("utf-8")

    fd, tmp_name = tempfile.mkstemp(prefix=".agent-", suffix=".tmp", dir=str(path.parent))
    tmp = pathlib.Path(tmp_name)
    try:
        # Restrict before writing any credential bytes.
        try:
            os.fchmod(fd, 0o600)
        except (AttributeError, OSError, NotImplementedError):
            pass
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _restrict_permissions(path)
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


def load_identity(path: pathlib.Path) -> Identity | None:
    try:
        return Identity.from_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"nimbusops-agent: corrupt identity file {path}: {exc}", file=sys.stderr)
        return None


def delete_identity(path: pathlib.Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def collect_host_info() -> dict:
    """Genuine host metadata from psutil/platform (no fabrication)."""
    vm = psutil.virtual_memory()
    return {
        "agent_version": __version__,
        "platform": platform.system(),
        "platform_release": platform.release(),
        "cpu_cores": psutil.cpu_count(logical=True),
        "total_memory_bytes": vm.total,
        "boot_time": None,  # Filled by collect_telemetry's psutil.boot_time().
    }
