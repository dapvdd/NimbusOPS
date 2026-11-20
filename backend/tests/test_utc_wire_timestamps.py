"""Preserve deployed SQLite UTC serialization without other candidate changes."""

from datetime import datetime, timezone

from backend.app.schemas import LatestMetrics


def test_sqlite_naive_server_time_is_explicit_utc():
    response = metrics(datetime(2026, 11, 20))
    assert response.model_dump(mode="json")["recorded_at"] == "2026-11-20T00:00:00Z"


def test_aware_server_time_remains_utc():
    response = metrics(datetime(2026, 11, 20, tzinfo=timezone.utc))
    assert response.model_dump(mode="json")["recorded_at"] == "2026-11-20T00:00:00Z"


def metrics(stamp):
    return LatestMetrics(
        recorded_at=stamp,
        cpu_percent=0,
        memory_used_bytes=1,
        memory_total_bytes=2,
        memory_used_percent=50,
        disk_used_bytes=1,
        disk_total_bytes=2,
        disk_used_percent=50,
    )
