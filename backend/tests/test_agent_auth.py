"""Agent endpoint authentication and validation tests."""

from backend.tests.conftest import auth_headers


def test_heartbeat_requires_auth(client, enrolled_host):
    host_id, _ = enrolled_host
    resp = client.post("/api/v1/agents/heartbeat", headers={"X-Host-Id": host_id}, json={})
    assert resp.status_code == 401

def test_heartbeat_wrong_token_rejected(client, enrolled_host):
    host_id, _ = enrolled_host
    resp = client.post(
        "/api/v1/agents/heartbeat",
        headers=auth_headers(host_id, "bad-token"),
        json={},
    )
    assert resp.status_code == 401


def test_heartbeat_token_for_other_host_rejected(client, enrolled_host):
    host_id, token = enrolled_host
    # Enroll a second host; try first host's token against second host id.
    r2 = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "other-host", "enrollment_token": "test-enroll-token"},
    )
    other_id = r2.json()["host_id"]
    resp = client.post(
        "/api/v1/agents/heartbeat",
        headers=auth_headers(other_id, token),
        json={},
    )
    assert resp.status_code == 401


def test_heartbeat_unknown_host_404(client):
    resp = client.post(
        "/api/v1/agents/heartbeat",
        headers=auth_headers("nonexistent-id", "whatever"),
        json={},
    )
    assert resp.status_code == 404


def test_heartbeat_success(client, enrolled_host):
    host_id, token = enrolled_host
    resp = client.post(
        "/api/v1/agents/heartbeat",
        headers=auth_headers(host_id, token),
        json={"agent_version": "0.1.0", "platform": "Linux", "cpu_cores": 2},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["host_id"] == host_id
    assert body["status"] == "ONLINE"


def test_telemetry_requires_auth(client, enrolled_host):
    host_id, _ = enrolled_host
    valid_body = {
        "recorded_at": "2026-11-08T12:00:00Z",
        "cpu_percent": 10.0,
        "memory_used_bytes": 1,
        "memory_total_bytes": 2,
        "disk_used_bytes": 1,
        "disk_total_bytes": 2,
    }
    resp = client.post("/api/v1/agents/telemetry", headers={"X-Host-Id": host_id}, json=valid_body)
    assert resp.status_code == 401


def test_telemetry_validation_rejects_out_of_bounds(client, enrolled_host):
    host_id, token = enrolled_host
    resp = client.post(
        "/api/v1/agents/telemetry",
        headers=auth_headers(host_id, token),
        json={
            "recorded_at": "2026-11-08T12:00:00Z",
            "cpu_percent": 150.0,
            "memory_used_bytes": 1,
            "memory_total_bytes": 2,
            "disk_used_bytes": 1,
            "disk_total_bytes": 2,
        },
    )
    assert resp.status_code == 422


def test_telemetry_rejects_used_gt_total(client, enrolled_host):
    host_id, token = enrolled_host
    resp = client.post(
        "/api/v1/agents/telemetry",
        headers=auth_headers(host_id, token),
        json={
            "recorded_at": "2026-11-08T12:00:00Z",
            "cpu_percent": 10.0,
            "memory_used_bytes": 5,
            "memory_total_bytes": 4,
            "disk_used_bytes": 1,
            "disk_total_bytes": 2,
        },
    )
    assert resp.status_code == 422
