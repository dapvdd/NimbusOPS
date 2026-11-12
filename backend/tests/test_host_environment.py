"""FR-19: host environment metadata (PRIVATE | PUBLIC-CLOUD), additive.

Default is PRIVATE; agents may report environment at enroll time; unknown
values are rejected (422).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_default_environment_is_private(client, enroll_token):
    r = client.post("/api/v1/agents/enroll",
                    json={"hostname": "env-default", "enrollment_token": enroll_token,
                          "agent_version": "0.1.0", "platform": "Linux",
                          "platform_release": "x", "cpu_cores": 1,
                          "total_memory_bytes": 1024})
    assert r.status_code == 200, r.text
    host_id = r.json()["host_id"]
    body = client.get(f"/api/v1/hosts/{host_id}").json()
    assert body["environment"] == "PRIVATE"


def test_enroll_with_public_cloud_environment(client, enroll_token):
    r = client.post("/api/v1/agents/enroll",
                    json={"hostname": "env-cloud", "enrollment_token": enroll_token,
                          "environment": "PUBLIC-CLOUD",
                          "agent_version": "0.1.0", "platform": "Linux",
                          "platform_release": "x", "cpu_cores": 1,
                          "total_memory_bytes": 1024})
    assert r.status_code == 200, r.text
    host_id = r.json()["host_id"]
    body = client.get(f"/api/v1/hosts/{host_id}").json()
    assert body["environment"] == "PUBLIC-CLOUD"


def test_enroll_unknown_environment_rejected(client, enroll_token):
    r = client.post("/api/v1/agents/enroll",
                    json={"hostname": "env-bad", "enrollment_token": enroll_token,
                          "environment": "MARS",
                          "agent_version": "0.1.0", "platform": "Linux",
                          "platform_release": "x", "cpu_cores": 1,
                          "total_memory_bytes": 1024})
    assert r.status_code == 422


def test_host_list_carries_environment(client, enroll_token):
    client.post("/api/v1/agents/enroll",
                json={"hostname": "env-list", "enrollment_token": enroll_token,
                      "environment": "PUBLIC-CLOUD",
                      "agent_version": "0.1.0", "platform": "Linux",
                      "platform_release": "x", "cpu_cores": 1,
                      "total_memory_bytes": 1024})
    body = client.get("/api/v1/hosts").json()
    match = [h for h in body["hosts"] if h["hostname"] == "env-list"]
    assert match and match[0]["environment"] == "PUBLIC-CLOUD"
