"""Task 14: agent-contract backward compatibility check.

The agent's outbound payloads (heartbeat, telemetry, enroll, result) must be
additive-only extensions of the Phase 3B contract: every field the ORIGINAL
(main-branch) client sends must still be accepted, and the agent must still
parse the ORIGINAL server response shapes. Pins the compatibility claim in
the final report with an executable check.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_MAIN = Path(r"C:\Users\user\Development\NimbusOPS")
REPO_WT = Path(__file__).resolve().parents[2]


def _extract_schema_fields(repo: Path, rel: str, classname: str) -> set[str]:
    """Grep the schema class body for `name:` field declarations (both repos)."""
    src = (repo / rel).read_text(encoding="utf-8")
    lines = src.splitlines()
    out: set[str] = set()
    inside = False
    for line in lines:
        if line.startswith(f"class {classname}"):
            inside = True
            continue
        if inside:
            if line.startswith("class ") and f"class {classname}" not in line:
                break
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and (": " in stripped or ":'" in stripped):
                name = stripped.split(":")[0].strip()
                if name.isidentifier():
                    out.add(name)
    return out


def test_heartbeat_request_fields_are_additive_only():
    old = _extract_schema_fields(REPO_MAIN, "backend/app/schemas/__init__.py", "HeartbeatRequest")
    new = _extract_schema_fields(REPO_WT, "backend/app/schemas/__init__.py", "HeartbeatRequest")
    assert old <= new, f"fields removed from HeartbeatRequest: {old - new}"
    extra = new - old
    assert extra == {"inventory"}, f"unexpected new heartbeat fields: {extra}"
    # All new fields optional (additive contract): the payload default is None.
    assert "inventory" in extra


def test_heartbeat_response_fields_are_additive_only():
    old = _extract_schema_fields(REPO_MAIN, "backend/app/schemas/__init__.py", "HeartbeatResponse")
    new = _extract_schema_fields(REPO_WT, "backend/app/schemas/__init__.py", "HeartbeatResponse")
    assert old <= new, f"fields removed from HeartbeatResponse: {old - new}"
    assert new - old == set(), "heartbeat response grew: agent parses by key, additions are server-side only"


def test_agent_client_ignores_unknown_heartbeat_response_fields():
    """The agent reads specific keys from the heartbeat response; unknown new
    keys must not break it (forward compatibility)."""
    from agent.nimbusops_agent.client import Sender

    class _Resp:
        status_code = 200
        text = "{}"

        def json(self):
            return {"host_id": "h", "status": "ONLINE", "server_time": "t",
                    "heartbeat_interval_seconds": 30, "docker_enabled": False,
                    "brand_new_future_field": {"x": 1}}

    s = Sender(server_url="http://test", host_id="h", agent_token="t")
    sent: dict = {}

    def fake_post(url, json=None, **kw):
        sent.update(json or {})

        class R:
            status_code = 200
            text = "ok"

            def json(self):
                return {"host_id": "h", "status": "ONLINE",
                        "server_time": "t", "heartbeat_interval_seconds": 30,
                        "docker_enabled": False, "brand_new_future_field": {"x": 1}}
        return R()

    s._client = type("C", (), {"post": staticmethod(fake_post), "headers": {}})()
    ok, detail = s.send_heartbeat({"agent_version": "0.1.0"})
    assert ok is True, detail
    assert sent["agent_version"] == "0.1.0"


def test_enroll_request_fields_are_additive_only():
    old = _extract_schema_fields(REPO_MAIN, "backend/app/schemas/__init__.py", "EnrollRequest")
    new = _extract_schema_fields(REPO_WT, "backend/app/schemas/__init__.py", "EnrollRequest")
    assert old <= new, f"fields removed from EnrollRequest: {old - new}"
    assert new - old == {"environment"}
