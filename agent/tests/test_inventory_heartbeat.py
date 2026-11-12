"""Phase 5 (FR-03): run_cycle attaches docker inventory to heartbeat.

Additive protocol check: when Docker is available, the heartbeat payload
carries `inventory` ({containers, observed_at}); when Docker is broken the
heartbeat still sends (inventory-less) and the loop never crashes.
"""

from __future__ import annotations

import json

import httpx
import pytest

import nimbusops_agent.main as agent_main
from nimbusops_agent.client import Sender


def _sender_capture(captured: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/heartbeat"):
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"retained": True})

    s = Sender(server_url="http://test", host_id="h1", agent_token="tok",
               sleep_fn=lambda _: None)
    s._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)
    return s


@pytest.fixture()
def _no_inventory_executor(monkeypatch):
    """Default: DockerExecutor stub returning a typed unavailable outcome."""
    class _Stub:
        def inventory(self):
            return {"status": "FAILED", "error_code": "DOCKER_UNAVAILABLE"}

    monkeypatch.setattr("nimbusops_agent.docker_exec.DockerExecutor", _Stub)


def test_run_cycle_inventory_attached_when_docker_ok(monkeypatch, _no_inventory_executor):
    captured: list[dict] = []

    class _Stub:
        def inventory(self):
            return {"status": "SUCCEEDED",
                    "result": {"containers": [{"id": "abc", "names": "nimbusops-x",
                                               "image": "nginx", "state": "running",
                                               "managed": True, "deployment_id": None}],
                               "observed_at": "2026-11-12T10:00:00+00:00"}}

    monkeypatch.setattr("nimbusops_agent.docker_exec.DockerExecutor", _Stub)
    s = _sender_capture(captured)
    ok, _detail = agent_main.run_cycle(s)
    assert ok is True
    inv = captured[0]["inventory"]
    assert inv["containers"][0]["id"] == "abc"
    assert "observed_at" in inv


def test_run_cycle_survives_broken_docker(monkeypatch, _no_inventory_executor):
    captured: list[dict] = []
    s = _sender_capture(captured)
    ok, _detail = agent_main.run_cycle(s)
    assert ok is True
    assert "inventory" not in captured[0]


def test_run_cycle_survives_inventory_exception(monkeypatch, _no_inventory_executor):
    class _Boom:
        def inventory(self):
            raise RuntimeError("docker exploded")

    monkeypatch.setattr("nimbusops_agent.docker_exec.DockerExecutor", _Boom)
    captured: list[dict] = []
    s = _sender_capture(captured)
    ok, _detail = agent_main.run_cycle(s)
    assert ok is True
    assert "inventory" not in captured[0]
