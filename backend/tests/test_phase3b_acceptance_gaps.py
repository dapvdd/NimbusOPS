"""Phase 3B final acceptance: gaps in automated coverage.

Covers acceptance items without dedicated prior tests:
- malformed/malicious Authorization headers on protected endpoints,
- malformed login JSON,
- concurrent bootstrap redemption (AC-11 pattern, single effect),
- oversized inputs.
"""

from __future__ import annotations

import concurrent.futures

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select


# --------------------------------------------------------------------------
# Malformed Authorization headers on an operator-protected endpoint
# --------------------------------------------------------------------------

def _issue_token(client: TestClient) -> str:
    from backend.app.core.security import hash_operator_password
    from backend.app.core.db import session_scope
    from backend.app.models import Operator
    from sqlalchemy import select as _sel
    from sqlalchemy.orm import Session as _Session  # noqa: F401

    with session_scope() as db:
        db.add(Operator(id="op-acc-1", username="acc_admin",
                        password_hash=hash_operator_password("pw-accept-1"),
                        role="ADMIN"))
    resp = client.post("/api/v1/operators/login",
                       json={"username": "acc_admin", "password": "pw-accept-1"})
    assert resp.status_code == 200, resp.text
    return resp.json()["session_token"]


def test_auth_header_without_bearer_scheme_rejected(client):
    tok = _issue_token(client)
    r = client.patch("/api/v1/hosts/5ca406e8-ee64-4e67-80b3-3c95abdf44ce",
                     headers={"Authorization": tok})  # no "Bearer "
    assert r.status_code == 401


def test_auth_header_empty_token_rejected(client):
    r = client.patch("/api/v1/hosts/5ca406e8-ee64-4e67-80b3-3c95abdf44ce",
                     headers={"Authorization": "Bearer "})
    assert r.status_code == 401


def test_auth_header_oversized_token_rejected(client):
    r = client.patch("/api/v1/hosts/5ca406e8-ee64-4e67-80b3-3c95abdf44ce",
                     headers={"Authorization": "Bearer " + "A" * 4096})
    assert r.status_code in (401, 413, 422)


def test_auth_header_latin1_escaped_token_rejected(client):
    # httpx headers must be latin-1-safe: exercise escaped high bytes, which
    # still must never authenticate and never 5xx.
    r = client.patch(
        "/api/v1/hosts/5ca406e8-ee64-4e67-80b3-3c95abdf44ce",
        headers={"Authorization": "Bearer caf\\u00e9\\u20ac"})
    assert r.status_code == 401


# --------------------------------------------------------------------------
# Malformed login payloads
# --------------------------------------------------------------------------

def test_login_missing_password_field_is_422(client):
    r = client.post("/api/v1/operators/login", json={"username": "acc_admin"})
    assert r.status_code == 422


def test_login_wrong_types_are_422(client):
    r = client.post("/api/v1/operators/login",
                    json={"username": 123, "password": ["x"]})
    assert r.status_code == 422


def test_login_unknown_username_401(client):
    r = client.post("/api/v1/operators/login",
                    json={"username": "ghost", "password": "whatever"})
    assert r.status_code == 401


# --------------------------------------------------------------------------
# Concurrent bootstrap redemption (AC-11 pattern)
# --------------------------------------------------------------------------

def test_bootstrap_concurrent_redemption_single_effect(client, enroll_token):
    tok = _issue_token(client)
    from backend.app.core.db import session_scope
    from backend.app.services import enrollment as enr

    from backend.app.core.security import hash_operator_password
    from backend.app.core.db import session_scope
    from backend.app.models import Operator
    from sqlalchemy import select as _sel
    from sqlalchemy.orm import Session as _Session  # noqa: F401

    with session_scope() as db:
        op = db.scalar(_sel(Operator).where(Operator.username == "acc_admin"))
        issued = enr.issue_bootstrap_token(
            db, op, hostname="race-host", expires_in_seconds=600)
        plaintext = issued[1]

    results: list[int] = []
    barrier = concurrent.futures.ThreadPoolExecutor(max_workers=8)

    def redeem(_: int) -> int:
        with TestClient(client.app) as c:  # independent session per thread
            r = c.post("/api/v1/agents/enroll",
                       json={"hostname": "race-host", "bootstrap_token": plaintext,
                             "agent_version": "0.1.0", "platform": "Linux",
                             "platform_release": "x", "cpu_cores": 1,
                             "total_memory_bytes": 1024})
            return r.status_code

    try:
        for code in barrier.map(redeem, range(32)):
            results.append(code)
    finally:
        barrier.shutdown()

    assert results.count(200) == 1, results
    assert all(c in (200, 409) for c in results), results
