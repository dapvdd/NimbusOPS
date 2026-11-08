"""Real psutil collection tests (genuine local system values)."""

from datetime import datetime, timezone

import psutil

from nimbusops_agent.telemetry import collect_telemetry, host_info_snapshot


def test_collect_telemetry_returns_real_values():
    t = collect_telemetry()
    # Real RAM: total must equal actual physical total.
    assert t["memory_total_bytes"] == psutil.virtual_memory().total
    # Bounds.
    assert 0.0 <= t["cpu_percent"] <= 100.0
    assert 0.0 <= t["memory_used_percent"] <= 100.0
    assert 0.0 <= t["disk_used_percent"] <= 100.0
    # used <= total
    assert t["memory_used_bytes"] <= t["memory_total_bytes"]
    assert t["disk_used_bytes"] <= t["disk_total_bytes"]
    # Real disk: total equals actual root filesystem total.
    assert t["disk_total_bytes"] == psutil.disk_usage("/").total
    # UTC timestamp close to now.
    delta = datetime.now(timezone.utc) - t["recorded_at"]
    assert abs(delta.total_seconds()) < 5


def test_host_info_snapshot_matches_system():
    info = host_info_snapshot()
    assert info["cpu_cores"] == psutil.cpu_count(logical=True)
    assert info["total_memory_bytes"] == psutil.virtual_memory().total
    assert info["platform"]
    assert info["agent_version"]
