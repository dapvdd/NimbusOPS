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
import sys
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
        if not self.enrollment_token:
            raise ConfigError("enrollment_token is required (never hardcode a default)")
        if not (MIN_INTERVAL <= self.interval <= MAX_INTERVAL):
            raise ConfigError(f"interval must be within [{MIN_INTERVAL}, {MAX_INTERVAL}] s")
        self.state_file = pathlib.Path(self.state_file)


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


def save_identity(path: pathlib.Path, identity: Identity) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(identity.to_json(), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Best-effort on Windows (POSIX perms not applicable).


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
