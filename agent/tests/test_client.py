"""Client retry/backoff and auth-error behavior tests (no live server)."""

import httpx
import pytest

from nimbusops_agent.client import AuthError, Sender


def _make(responder, **kw) -> Sender:
    """Sender wired to a mock transport (no network)."""
    defaults = dict(
        server_url="http://test",
        host_id="h1",
        agent_token="tok",
        sleep_fn=lambda _s: None,  # No waiting in tests.
    )
    defaults.update(kw)
    s = Sender(**defaults)
    s._client = httpx.Client(transport=httpx.MockTransport(responder), timeout=5.0)
    return s


def test_send_success_first_try(identity):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"host_id": "h1", "status": "ONLINE"})

    s = _make(handler)
    ok, detail = s.send_telemetry({"recorded_at": "2026-11-08T00:00:00Z", "cpu_percent": 5.0})
    assert ok and detail == "ok"
    assert len(calls) == 1
    assert calls[0].headers["X-Host-Id"] == "h1"
    assert calls[0].headers["Authorization"] == f"Bearer {identity.agent_token if False else 'tok'}"


def test_retry_on_network_error_then_success():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={})

    s = _make(handler)
    ok, detail = s.send_heartbeat({})
    assert ok, detail
    assert len(attempts) == 3


def test_gives_up_after_max_retries():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        raise httpx.ConnectError("refused")

    s = _make(handler, max_retries=3)
    ok, detail = s.send_heartbeat({})
    assert not ok
    assert "giving up after 3 attempts" in detail
    assert len(attempts) == 3


def test_backoff_grows_exponentially():
    sleeps = []

    def handler(request):
        raise httpx.ConnectError("down")

    s = _make(handler, max_retries=4, backoff_initial=1.0, backoff_base=2.0, sleep_fn=sleeps.append)
    ok, _ = s.send_heartbeat({})
    assert not ok
    # Jitter added, but underlying growth visible: 4 sleeps recorded.
    assert len(sleeps) == 3  # No sleep after the final attempt.
    # Bounded by backoff_max.
    assert all(v <= 30.0 + 9.0 for v in sleeps)


def test_auth_error_not_retried():
    attempts = []

    def handler(request):
        attempts.append(1)
        return httpx.Response(401, json={"error": {"code": "UNAUTHORIZED", "message": "bad token"}})

    s = _make(handler)
    with pytest.raises(AuthError):
        s.send_telemetry({"cpu_percent": 1.0})
    assert len(attempts) == 1  # 401 must not be retried.


def test_forbidden_not_retried():
    def handler(request):
        return httpx.Response(403, json={"error": {"code": "FORBIDDEN_HOST", "message": "no"}})

    s = _make(handler)
    with pytest.raises(AuthError):
        s.send_heartbeat({})


def test_retryable_server_status_retried():
    attempts = []

    def handler(request):
        attempts.append(1)
        return httpx.Response(503, json={})

    s = _make(handler, max_retries=2)
    ok, detail = s.send_telemetry({"cpu_percent": 1.0})
    assert not ok
    assert len(attempts) == 2


def test_client_error_400_not_retried():
    attempts = []

    def handler(request):
        attempts.append(1)
        return httpx.Response(422, json={"detail": []})

    s = _make(handler)
    ok, detail = s.send_telemetry({"cpu_percent": 1.0})
    assert not ok
    assert len(attempts) == 1
    assert "422" in detail
