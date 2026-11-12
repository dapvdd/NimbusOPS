"""FR-09: host list pagination and filtering (additive query params).

Back-compat pin: no params → legacy HostListResponse shape (hosts + count).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _make_hosts(client: TestClient, n: int) -> None:
    from backend.app.core.db import session_scope
    from backend.app.core.security import hash_token
    from backend.app.models import Host

    with session_scope() as db:
        for i in range(n):
            db.add(Host(
                id=f"pag-{i:03d}-0000-0000-0000-000000000000",
                hostname=f"fleet-{i:03d}.example.test",
                agent_token_hash=hash_token(f"tok-{i}"),
                enrollment_status="ENROLLED",
                last_seen_at=None,
            ))


def test_no_params_returns_legacy_shape(client):
    _make_hosts(client, 3)
    r = client.get("/api/v1/hosts")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    assert len(body["hosts"]) == 3
    # Legacy consumers must keep working: hosts[] entries carry hostname.
    assert {h["hostname"] for h in body["hosts"]} == {
        "fleet-000.example.test", "fleet-001.example.test", "fleet-002.example.test"}


def test_pagination_page2_size10(client):
    _make_hosts(client, 25)
    r = client.get("/api/v1/hosts", params={"page": 2, "page_size": 10})
    assert r.status_code == 200
    body = r.json()
    assert len(body["hosts"]) == 10
    assert body["count"] == 25          # legacy count = total
    meta = body["pagination"]
    assert meta == {"page": 2, "page_size": 10, "total": 25, "total_pages": 3}


def test_pagination_last_partial_page(client):
    _make_hosts(client, 25)
    r = client.get("/api/v1/hosts", params={"page": 3, "page_size": 10})
    body = r.json()
    assert len(body["hosts"]) == 5
    assert body["pagination"]["total_pages"] == 3


def test_hostname_filter_substring(client):
    _make_hosts(client, 10)
    r = client.get("/api/v1/hosts", params={"hostname": "fleet-00"})
    body = r.json()
    assert body["count"] == 10  # fleet-000..009 all contain fleet-00
    r2 = client.get("/api/v1/hosts", params={"hostname": "fleet-009"})
    assert r2.json()["count"] == 1


def test_hostname_filter_no_match_empty(client):
    _make_hosts(client, 5)
    body = client.get("/api/v1/hosts", params={"hostname": "nomatch"}).json()
    assert body["count"] == 0
    assert body["hosts"] == []


def test_pagination_params_validated(client):
    r = client.get("/api/v1/hosts", params={"page": 0})
    assert r.status_code == 422
    r2 = client.get("/api/v1/hosts", params={"page_size": 0})
    assert r2.status_code == 422
    r3 = client.get("/api/v1/hosts", params={"page_size": 500})
    assert r3.status_code == 422  # max 200
