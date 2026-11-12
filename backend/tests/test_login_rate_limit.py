"""Phase 6: login rate limiting (threat model limitation 6).

Sliding window per username: N failed attempts within the window → 429
RATE_LIMITED until the window expires. Successful login resets the counter.
Knobs come from settings (test overrides them via env).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_rate_limiter():
    """The limiter is process-global; clear it between tests."""
    from backend.app.api.operators import _login_attempts
    _login_attempts.clear()
    yield
    _login_attempts.clear()


def _seed_operator(client: TestClient) -> None:
    from backend.app.core.db import session_scope
    from backend.app.core.security import hash_operator_password
    from backend.app.models import Operator

    with session_scope() as db:
        db.add(Operator(id="op-rl", username="rl_admin",
                        password_hash=hash_operator_password("pw-rl"),
                        role="ADMIN"))


def test_failed_logins_within_window_trigger_429(client):
    _seed_operator(client)
    codes = []
    for _ in range(6):
        r = client.post("/api/v1/operators/login",
                        json={"username": "rl_admin", "password": "wrong"})
        codes.append(r.status_code)
    # First N-1 are 401, the 6th is rate limited (limit=5 default).
    assert codes[:5] == [401] * 5, codes
    assert codes[5] == 429, codes
    body = client.post("/api/v1/operators/login",
                       json={"username": "rl_admin", "password": "wrong"}).json()
    assert body["error"]["code"] == "RATE_LIMITED"


def test_successful_login_resets_counter(client):
    _seed_operator(client)
    for _ in range(4):
        client.post("/api/v1/operators/login",
                    json={"username": "rl_admin", "password": "wrong"})
    r = client.post("/api/v1/operators/login",
                    json={"username": "rl_admin", "password": "pw-rl"})
    assert r.status_code == 200
    # Counter reset: the window restarts, so 5 failures are allowed again and
    # the 6th (of the new window) is rate limited — same budget as test 1.
    codes = []
    for _ in range(6):
        codes.append(client.post("/api/v1/operators/login",
                                 json={"username": "rl_admin", "password": "wrong"}).status_code)
    assert codes[:5] == [401] * 5, codes
    assert codes[5] == 429, codes


def test_rate_limit_is_per_username(client):
    _seed_operator(client)
    for _ in range(5):
        client.post("/api/v1/operators/login",
                    json={"username": "rl_admin", "password": "wrong"})
    # A different username is not affected.
    r = client.post("/api/v1/operators/login",
                    json={"username": "rl_admin2", "password": "wrong"})
    assert r.status_code == 401  # not 429


def test_correct_credentials_after_limit_still_429(client):
    """Fail closed: even the right password is rejected while limited."""
    _seed_operator(client)
    for _ in range(6):
        client.post("/api/v1/operators/login",
                    json={"username": "rl_admin", "password": "wrong"})
    r = client.post("/api/v1/operators/login",
                    json={"username": "rl_admin", "password": "pw-rl"})
    assert r.status_code == 429


def test_rate_limit_body_is_username_agnostic(client):
    """429 body must not differ between known and unknown usernames
    (no username-existence oracle via the limiter)."""
    _seed_operator(client)
    for _ in range(6):
        client.post("/api/v1/operators/login",
                    json={"username": "rl_admin", "password": "wrong"})
    for _ in range(6):
        client.post("/api/v1/operators/login",
                    json={"username": "ghost-user", "password": "wrong"})
    known = client.post("/api/v1/operators/login",
                        json={"username": "rl_admin", "password": "wrong"})
    unknown = client.post("/api/v1/operators/login",
                          json={"username": "ghost-user", "password": "wrong"})
    assert known.status_code == unknown.status_code == 429
    assert known.json() == unknown.json()
