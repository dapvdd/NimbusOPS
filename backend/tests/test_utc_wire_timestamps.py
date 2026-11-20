"""SQLite UTC values must remain unambiguous on the browser wire."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.schemas import HostOut, LatestMetrics


@pytest.mark.parametrize("offset", [None, timezone.utc, timezone(timedelta(hours=7))])
def test_metrics_wire_timestamp_has_explicit_utc(offset: timezone | None) -> None:
    stamp = datetime(
        2026, 11, 20, 3 if offset != timezone(timedelta(hours=7)) else 10, tzinfo=offset
    )
    point = LatestMetrics(
        recorded_at=stamp,
        cpu_percent=0,
        memory_used_bytes=1,
        memory_total_bytes=2,
        memory_used_percent=50,
        disk_used_bytes=1,
        disk_total_bytes=4,
        disk_used_percent=25,
    )
    wire = json.loads(point.model_dump_json())["recorded_at"]
    assert wire == "2026-11-20T03:00:00Z"


def test_host_wire_timestamps_preserve_sqlite_utc_and_nulls() -> None:
    # Deliberately reproduce SQLite's timezone-naive persisted UTC shape.
    stamp = datetime(2026, 11, 20, 3, tzinfo=None)  # noqa: DTZ001
    host = HostOut(
        id="test",
        hostname="azure",
        status="ONLINE",
        connectivity="ONLINE",
        agent_version=None,
        platform=None,
        platform_release=None,
        cpu_cores=None,
        total_memory_bytes=None,
        boot_time=stamp,
        enrolled_at=stamp,
        last_seen_at=stamp,
        last_telemetry_at=stamp,
        latest_metrics=None,
        is_revoked=False,
        enrollment_status="ENROLLED",
        docker_enabled=False,
        environment="PUBLIC-CLOUD",
        agent_mode=None,
        credential_version=1,
        credential_grace_until=None,
    )
    wire = json.loads(host.model_dump_json())
    for field in ("boot_time", "enrolled_at", "last_seen_at", "last_telemetry_at"):
        assert wire[field] == "2026-11-20T03:00:00Z"
    assert wire["credential_grace_until"] is None
