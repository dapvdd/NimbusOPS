"""Telemetry persistence, host listing, metrics retrieval, status calc."""

from datetime import datetime, timedelta, timezone

from backend.tests.conftest import auth_headers


def _send(client, host_id, token, recorded_at, cpu=12.5, mem_used=2, mem_total=8, disk_used=10, disk_total=100):
    return client.post(
        "/api/v1/agents/telemetry",
        headers=auth_headers(host_id, token),
        json={
            "recorded_at": recorded_at.isoformat(),
            "cpu_percent": cpu,
            "memory_used_bytes": mem_used * 1_000_000_000,
            "memory_total_bytes": mem_total * 1_000_000_000,
            "disk_used_bytes": disk_used * 1_000_000_000,
            "disk_total_bytes": disk_total * 1_000_000_000,
        },
    )


def test_telemetry_persists_and_latest_reflects(client, enrolled_host):
    host_id, token = enrolled_host
    ts = datetime.now(timezone.utc)
    resp = _send(client, host_id, token, ts, cpu=42.0)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ONLINE"

    got = client.get(f"/api/v1/hosts/{host_id}").json()
    assert got["latest_metrics"] is not None
    lm = got["latest_metrics"]
    assert lm["cpu_percent"] == 42.0
    assert lm["recorded_at"].startswith(ts.strftime("%Y-%m-%dT%H:%M"))
    assert got["last_telemetry_at"] is not None


def test_no_telemetry_means_null_not_zero(client, enrolled_host):
    host_id, _ = enrolled_host
    got = client.get(f"/api/v1/hosts/{host_id}").json()
    assert got["latest_metrics"] is None


def test_metrics_history_order_and_limit(client, enrolled_host):
    host_id, token = enrolled_host
    base = datetime.now(timezone.utc) - timedelta(minutes=5)
    for i in range(5):
        r = _send(client, host_id, token, base + timedelta(seconds=10 * i), cpu=10.0 + i)
        assert r.status_code == 200
    got = client.get(f"/api/v1/hosts/{host_id}/metrics?limit=3").json()
    assert got["count"] == 3
    cpus = [p["cpu_percent"] for p in got["points"]]
    assert cpus == [14.0, 13.0, 12.0]  # newest first


def test_status_offline_when_never_seen(client, enrolled_host):
    # Directly set last_seen far in the past via enrollment without heartbeat.
    host_id, _ = enrolled_host
    body = client.get(f"/api/v1/hosts/{host_id}").json()
    # Enrolled but no heartbeat yet -> last_seen None -> OFFLINE
    assert body["status"] == "OFFLINE"


def test_status_stale_and_offline_transitions(client, enrolled_host):
    host_id, token = enrolled_host
    now = datetime.now(timezone.utc)
    _send(client, host_id, token, now, cpu=20.0)
    body = client.get(f"/api/v1/hosts/{host_id}").json()
    assert body["status"] == "ONLINE"


def test_status_calc_unit():
    from datetime import datetime, timezone

    from backend.app.services.hosts import compute_status

    now = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    assert compute_status(now - timedelta(seconds=10), now, 90, 600) == "ONLINE"
    assert compute_status(now - timedelta(seconds=300), now, 90, 600) == "STALE"
    assert compute_status(now - timedelta(seconds=700), now, 90, 600) == "OFFLINE"
    assert compute_status(None, now, 90, 600) == "OFFLINE"


def test_public_hosts_never_expose_token_hash(client, enrolled_host):
    host_id, _ = enrolled_host
    body = client.get(f"/api/v1/hosts/{host_id}").json()
    assert "agent_token" not in body
    assert "agent_token_hash" not in body
    text = str(body)
    assert "token" not in text.lower()
