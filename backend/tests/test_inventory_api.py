"""FR-03: agent docker inventory snapshots — persist on heartbeat, read via API.

Stale data honesty: the response carries observed_at + age_seconds; a missing
snapshot is a structured 404, never fabricated.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _enroll(client: TestClient) -> tuple[str, str]:
    r = client.post("/api/v1/agents/enroll",
                    json={"hostname": "inv-host", "enrollment_token": "test-enroll-token",
                          "agent_version": "0.1.0", "platform": "Linux",
                          "platform_release": "x", "cpu_cores": 1,
                          "total_memory_bytes": 1024})
    assert r.status_code == 200, r.text
    return r.json()["host_id"], r.json()["agent_token"]


def _beat(client: TestClient, host_id: str, token: str, extra: dict | None = None) -> None:
    payload = {"agent_version": "0.1.0", "platform": "Linux",
               "platform_release": "x", "cpu_cores": 1,
               "total_memory_bytes": 1024}
    payload.update(extra or {})
    r = client.post("/api/v1/agents/heartbeat", json=payload,
                    headers={"X-Host-Id": host_id, "Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text


def test_inventory_snapshot_404_when_none(client):
    host_id, token = _enroll(client)
    _beat(client, host_id, token)
    r = client.get(f"/api/v1/hosts/{host_id}/inventory")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "INVENTORY_NOT_FOUND"


def test_heartbeat_with_inventory_persists_snapshot(client):
    host_id, token = _enroll(client)
    _beat(client, host_id, token, extra={"inventory": {
        "containers": [
            {"id": "abc123", "names": "nimbusops-nginx-demo-x",
             "image": "nginx:1.27-alpine", "state": "running",
             "managed": True, "deployment_id": "d1"},
            {"id": "def456", "names": "unrelated", "image": "busybox",
             "state": "exited", "managed": False, "deployment_id": None},
        ],
        "observed_at": "2026-11-12T10:00:00Z",
    }})
    r = client.get(f"/api/v1/hosts/{host_id}/inventory")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["host_id"] == host_id
    assert len(body["containers"]) == 2
    assert body["containers"][0]["managed"] is True
    assert "observed_at" in body
    assert "age_seconds" in body
    assert body["age_seconds"] >= 0


def test_second_heartbeat_replaces_snapshot(client):
    host_id, token = _enroll(client)
    _beat(client, host_id, token, extra={"inventory": {
        "containers": [{"id": "old", "names": "a", "image": "i", "state": "running",
                        "managed": True, "deployment_id": None}],
        "observed_at": "2026-11-12T10:00:00Z"}})
    _beat(client, host_id, token, extra={"inventory": {
        "containers": [{"id": "new", "names": "b", "image": "i", "state": "exited",
                        "managed": False, "deployment_id": None}],
        "observed_at": "2026-11-12T10:05:00Z"}})
    body = client.get(f"/api/v1/hosts/{host_id}/inventory").json()
    assert len(body["containers"]) == 1
    assert body["containers"][0]["id"] == "new"


def test_heartbeat_without_inventory_keeps_last_snapshot(client):
    host_id, token = _enroll(client)
    _beat(client, host_id, token, extra={"inventory": {
        "containers": [{"id": "keep", "names": "a", "image": "i", "state": "running",
                        "managed": True, "deployment_id": None}],
        "observed_at": "2026-11-12T10:00:00Z"}})
    _beat(client, host_id, token)  # no inventory field
    body = client.get(f"/api/v1/hosts/{host_id}/inventory").json()
    assert len(body["containers"]) == 1
    assert body["containers"][0]["id"] == "keep"


def test_inventory_requires_valid_host_auth(client):
    host_id, token = _enroll(client)
    r = client.get("/api/v1/hosts/00000000-0000-0000-0000-000000000000/inventory")
    assert r.status_code == 404
