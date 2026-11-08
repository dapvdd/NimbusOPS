"""Main-loop behavior: enrollment flow, auth rejection, graceful stop."""

import json

import httpx
import pytest

import nimbusops_agent.main as agent_main
from nimbusops_agent.config import Config, Identity
from nimbusops_agent.main import ensure_enrolled, run


def _cfg(tmp_path, server="http://test", interval=30.0):
    return Config(server_url=server, enrollment_token="tok-enroll", interval=interval, state_file=tmp_path / "a.json")


def _sender_factory(responder, calls):
    from nimbusops_agent.client import Sender

    def factory(**kw):
        s = Sender(server_url=kw.get("server_url", "http://test"), host_id=kw.get("host_id", ""), agent_token=kw.get("agent_token", ""), sleep_fn=lambda _: None)
        s._client = httpx.Client(transport=httpx.MockTransport(responder), timeout=5.0)
        calls.append(kw)
        return s

    return factory


def _seed_identity(cfg):
    from nimbusops_agent.config import save_identity

    save_identity(cfg.state_file, Identity(host_id="h1", agent_token="tok"))


@pytest.fixture(autouse=True)
def _reset_stop():
    agent_main._stop["requested"] = False
    yield
    agent_main._stop["requested"] = False


def test_ensure_enrolled_persists_identity(tmp_path, monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/agents/enroll"
        body = json.loads(request.content)
        assert body["hostname"]
        assert body["enrollment_token"] == "tok-enroll"
        return httpx.Response(200, json={"host_id": "h-123", "agent_token": "agent-tok"})

    monkeypatch.setattr(agent_main, "Sender", _sender_factory(handler, calls))
    cfg = _cfg(tmp_path)
    identity, created = ensure_enrolled(cfg)
    assert created is True
    assert identity.host_id == "h-123"
    # Second call reuses the stored identity (no second enroll request).
    identity2, created2 = ensure_enrolled(cfg)
    assert created2 is False
    assert identity2.host_id == "h-123"
    assert len(calls) == 1


def test_ensure_enrolled_failure_propagates(tmp_path, monkeypatch):
    def handler(request):
        return httpx.Response(503, json={})

    monkeypatch.setattr(agent_main, "Sender", _sender_factory(handler, []))
    with pytest.raises(RuntimeError, match="enrollment failed"):
        ensure_enrolled(_cfg(tmp_path))


def test_run_exits_code3_when_credentials_rejected(tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": "UNAUTHORIZED", "message": "no"}})

    monkeypatch.setattr(agent_main, "Sender", _sender_factory(handler, []))
    monkeypatch.setattr(agent_main, "install_signal_handlers", lambda: None)
    # Pre-seed identity so we skip enrollment (enrollment would 401 too).
    cfg = _cfg(tmp_path)
    _seed_identity(cfg)
    code = run(cfg)
    assert code == 3


def test_run_graceful_stop_after_one_cycle(tmp_path, monkeypatch):
    telem_posts = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/heartbeat"):
            return httpx.Response(200, json={})
        telem_posts.append(json.loads(request.content))
        return httpx.Response(200, json={"retained": True})

    monkeypatch.setattr(agent_main, "Sender", _sender_factory(handler, []))
    monkeypatch.setattr(agent_main, "install_signal_handlers", lambda: None)
    cfg = _cfg(tmp_path, interval=30.0)
    _seed_identity(cfg)
    # Simulate Ctrl+I arriving shortly after start.
    def stop_after(_seconds):
        agent_main._stop["requested"] = True

    import time as _time

    monkeypatch.setattr(_time, "sleep", stop_after)
    monkeypatch.setattr(agent_main.time, "sleep", stop_after)
    code = run(cfg)
    assert code == 0
    assert len(telem_posts) >= 1
    payload = telem_posts[0]
    assert 0.0 <= payload["cpu_percent"] <= 100.0
    assert payload["memory_total_bytes"] > 0
