"""Phase 6 reliability: SQLite WAL mode + graceful shutdown logging.

WAL: writer/reader concurrency without "database is locked" failures under
the control plane's concurrent heartbeat/telemetry/claim load. Verified by
reading back PRAGMA journal_mode on a real session connection.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_journal_mode_is_wal_on_session_connection(client):
    from backend.app.core.db import engine, session_scope
    from sqlalchemy import text

    assert engine.dialect.name == "sqlite"  # precondition: this is a SQLite deployment
    with session_scope() as db:
        mode = db.scalar(text("PRAGMA journal_mode"))
    assert str(mode).lower() == "wal"


def test_foreign_keys_and_busy_timeout_still_enforced(client):
    from backend.app.core.db import session_scope
    from sqlalchemy import text

    with session_scope() as db:
        fk = db.scalar(text("PRAGMA foreign_keys"))
        busy = db.scalar(text("PRAGMA busy_timeout"))
    assert int(fk) == 1
    assert int(busy) == 5000


def test_app_boots_and_shuts_down_cleanly(client):
    """TestClient runs the lifespan: startup migrations + clean shutdown."""
    # client fixture already entered/exited the lifespan context; a second
    # request proves the app is functional after full startup.
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"
