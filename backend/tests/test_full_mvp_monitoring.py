"""Disposable monitoring and SQLite recovery evidence; no external services."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.core.db import engine
from backend.app.core.migrations import run_sprint5_migrations, upgrade_phase3b
from backend.app.core.security import generate_agent_token, hash_session_token
from backend.app.models import Host, Operator, OperatorSession, Telemetry
from backend.app.services.hosts import authenticate_host
from backend.tests.conftest import auth_headers


def _viewer(db: Session) -> dict[str, str]:
    """Create a disposable read-only session without bypassing authorization."""
    token = generate_agent_token()
    operator = Operator(
        username="mvp-evidence", password_hash="not-loginable", role="VIEWER"
    )
    db.add(operator)
    db.flush()
    db.add(
        OperatorSession(
            operator_id=operator.id,
            token_hash=hash_session_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    db.commit()
    return {"Authorization": f"Bearer {token}"}


def test_full_mvp_api_connectivity_transitions_and_recovery(
    client: TestClient,
    enrolled_host: tuple[str, str],
    db_session: Session,
) -> None:
    """Exercise read API transitions by aging only a disposable host row."""
    host_id, token = enrolled_host
    headers = _viewer(db_session)
    url = f"/api/v1/hosts/{host_id}"
    assert client.get(url, headers=headers).json()["status"] == "OFFLINE"
    assert (
        client.post(
            "/api/v1/agents/heartbeat", json={}, headers=auth_headers(host_id, token)
        ).status_code
        == 200
    )
    assert client.get(url, headers=headers).json()["status"] == "ONLINE"
    for age, expected in ((120, "STALE"), (700, "OFFLINE")):
        host = db_session.get(Host, host_id)
        assert host is not None
        host.last_seen_at = datetime.now(timezone.utc) - timedelta(seconds=age)
        db_session.commit()
        assert client.get(url, headers=headers).json()["status"] == expected
    assert (
        client.post(
            "/api/v1/agents/heartbeat", json={}, headers=auth_headers(host_id, token)
        ).status_code
        == 200
    )
    assert client.get(url, headers=headers).json()["status"] == "ONLINE"


def test_full_mvp_telemetry_duplicate_characterization_and_retention(
    client: TestClient,
    enrolled_host: tuple[str, str],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated telemetry is accepted, not replay-protected; retention stays bounded."""
    from backend.app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "telemetry_retention_rows", 2)
    host_id, token = enrolled_host
    payload = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "cpu_percent": 12.5,
        "memory_used_bytes": 1,
        "memory_total_bytes": 2,
        "disk_used_bytes": 1,
        "disk_total_bytes": 2,
    }
    for _ in range(3):
        response = client.post(
            "/api/v1/agents/telemetry",
            json=payload,
            headers=auth_headers(host_id, token),
        )
        assert response.status_code == 200
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Telemetry)
            .where(Telemetry.host_id == host_id)
        )
        == 2
    )


@pytest.mark.parametrize("naive", [False, True])
def test_full_mvp_future_telemetry_cannot_poison_latest_or_liveness(
    client: TestClient,
    enrolled_host: tuple[str, str],
    db_session: Session,
    naive: bool,
) -> None:
    """Reject gross clock skew before storage or refreshing host connectivity."""
    host_id, token = enrolled_host
    viewer = _viewer(db_session)
    future = datetime.now(timezone.utc) + timedelta(days=365)
    if naive:
        future = future.replace(tzinfo=None)
    payload = {
        "recorded_at": future.isoformat(),
        "cpu_percent": 99.0,
        "memory_used_bytes": 1,
        "memory_total_bytes": 2,
        "disk_used_bytes": 1,
        "disk_total_bytes": 2,
    }
    response = client.post(
        "/api/v1/agents/telemetry",
        json=payload,
        headers=auth_headers(host_id, token),
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "recorded_at"]
    host = client.get(f"/api/v1/hosts/{host_id}", headers=viewer).json()
    assert host["status"] == "OFFLINE"
    assert host["latest_metrics"] is None
    payload.update(recorded_at=datetime.now(timezone.utc).isoformat(), cpu_percent=12.5)
    assert (
        client.post(
            "/api/v1/agents/telemetry",
            json=payload,
            headers=auth_headers(host_id, token),
        ).status_code
        == 200
    )
    host = client.get(f"/api/v1/hosts/{host_id}", headers=viewer).json()
    assert host["latest_metrics"]["cpu_percent"] == 12.5


@pytest.mark.parametrize("offset_seconds", [-86400, 0, 240])
def test_full_mvp_delayed_and_small_skew_samples_preserve_receipt_liveness(
    client: TestClient,
    enrolled_host: tuple[str, str],
    db_session: Session,
    offset_seconds: int,
) -> None:
    """Old samples remain valid and cannot move receipt-based liveness backward."""
    host_id, token = enrolled_host
    viewer = _viewer(db_session)
    before = datetime.now(timezone.utc)
    timestamp = before + timedelta(seconds=offset_seconds)
    # A non-UTC offset must describe the same instant when stored/returned.
    timestamp = timestamp.astimezone(timezone(timedelta(hours=7)))
    response = client.post(
        "/api/v1/agents/telemetry",
        headers=auth_headers(host_id, token),
        json={
            "recorded_at": timestamp.isoformat(),
            "cpu_percent": 15.0,
            "memory_used_bytes": 1,
            "memory_total_bytes": 2,
            "disk_used_bytes": 1,
            "disk_total_bytes": 2,
        },
    )
    assert response.status_code == 200
    returned = datetime.fromisoformat(
        response.json()["recorded_at"].replace("Z", "+00:00")
    )
    assert returned == timestamp
    host = client.get(f"/api/v1/hosts/{host_id}", headers=viewer).json()
    assert host["status"] == "ONLINE"
    last_seen = datetime.fromisoformat(host["last_seen_at"].replace("Z", "+00:00"))
    assert before <= last_seen <= datetime.now(timezone.utc)


def test_full_mvp_sqlite_online_backup_restore_identity_and_migrations(
    client: TestClient,
    enrolled_host: tuple[str, str],
    tmp_path: Path,
) -> None:
    """Back up fixture WAL DB via SQLite API, restore fresh file, rerun migrations."""
    host_id, token = enrolled_host
    assert (
        client.post(
            "/api/v1/agents/heartbeat", json={}, headers=auth_headers(host_id, token)
        ).status_code
        == 200
    )
    response = client.post(
        "/api/v1/agents/telemetry",
        headers=auth_headers(host_id, token),
        json={
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "cpu_percent": 42.0,
            "memory_used_bytes": 1,
            "memory_total_bytes": 2,
            "disk_used_bytes": 1,
            "disk_total_bytes": 2,
        },
    )
    assert response.status_code == 200
    assert engine.url.database is not None
    backup = tmp_path / "full-mvp-backup.sqlite3"
    restored = tmp_path / "full-mvp-restored.sqlite3"
    with sqlite3.connect(engine.url.database) as source, sqlite3.connect(
        backup
    ) as target:
        source.backup(target)
        before = list(target.iterdump())
        assert target.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    with sqlite3.connect(backup) as source, sqlite3.connect(restored) as target:
        source.backup(target)
        assert list(target.iterdump()) == before
        assert target.execute("PRAGMA foreign_key_check").fetchall() == []
    url = f"sqlite:///{restored.as_posix()}"
    for _ in range(2):
        upgrade_phase3b(url)
        run_sprint5_migrations(url)
    restored_engine = create_engine(url)
    try:
        with Session(restored_engine) as db:
            host = authenticate_host(db, host_id, token)
            assert host.id == host_id
            assert host.last_seen_at is not None
            metric = db.scalar(select(Telemetry).where(Telemetry.host_id == host_id))
            assert metric is not None
            assert metric.cpu_percent == 42.0
        with sqlite3.connect(restored) as conn:
            assert list(conn.iterdump()) == before
            assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        restored_engine.dispose()
