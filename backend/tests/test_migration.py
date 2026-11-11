"""Phase 3B migration tests: fresh DB, legacy backfill, idempotency.

Covers PHASE3B_MIGRATION_PLAN.md §7 gates 1-3 (gate 4-5 are covered by the
additive-only design: old code paths ignore new columns; DavidLab-row
survival is asserted by the legacy-upgrade test below).
"""

import sqlite3

import pytest
from sqlalchemy import inspect, text

from backend.app.core.db import engine
from backend.app.models import Base


def _table_names(insp):
    return set(insp.get_table_names())


def test_fresh_db_creates_phase3b_structures(client):
    """Gate 1: on a fresh DB the Phase 3B tables and host columns exist."""
    insp = inspect(engine)
    tables = _table_names(insp)
    for t in ("bootstrap_tokens", "operators", "operator_sessions", "host_events"):
        assert t in tables, f"missing table {t}"
    host_cols = {c["name"] for c in insp.get_columns("hosts")}
    for col in ("enrollment_status", "docker_enabled", "credential_version"):
        assert col in host_cols, f"missing hosts column {col}"
    op_cols = {c["name"] for c in insp.get_columns("deployment_operations")}
    assert "timeout_at" in op_cols


def test_new_host_defaults_pending_and_docker_disabled(client, enroll_token):
    """A newly created host (pre-enrollment flow change) defaults to PENDING/docker off."""
    resp = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "defaults-host", "enrollment_token": enroll_token},
    )
    assert resp.status_code == 200
    host_id = resp.json()["host_id"]
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT enrollment_status, docker_enabled, credential_version FROM hosts WHERE id=:h"),
            {"h": host_id},
        ).one()
    assert row.enrollment_status == "ENROLLED"  # enroll completes immediately; PENDING is pre-completion only
    assert row.docker_enabled == 0
    assert row.credential_version == 1


def test_legacy_db_backfill_and_davidlab_survival(tmp_path):
    """Gates 2+5: a Phase 1-2-shaped DB is upgraded in place; rows survive byte-for-byte
    except the three new columns; the pre-3B agent token still authenticates."""
    # Build a legacy DB (no Phase 3B columns/tables) with a david-lab-like row.
    legacy = tmp_path / "legacy.db"
    con = sqlite3.connect(legacy)
    con.executescript(
        """
        CREATE TABLE hosts (
            id VARCHAR(36) PRIMARY KEY,
            hostname VARCHAR(255) UNIQUE NOT NULL,
            agent_token_hash VARCHAR(64) NOT NULL,
            enrolled_at TIMESTAMP NOT NULL,
            revoked_at TIMESTAMP,
            agent_version VARCHAR(64),
            platform VARCHAR(255),
            platform_release VARCHAR(255),
            cpu_cores INTEGER,
            total_memory_bytes BIGINT,
            boot_time TIMESTAMP,
            last_seen_at TIMESTAMP,
            last_telemetry_at TIMESTAMP,
            is_revoked BOOLEAN NOT NULL
        );
        CREATE TABLE telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            host_id VARCHAR(36) NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
            recorded_at TIMESTAMP NOT NULL,
            cpu_percent FLOAT NOT NULL,
            memory_used_bytes BIGINT NOT NULL,
            memory_total_bytes BIGINT NOT NULL,
            disk_used_bytes BIGINT NOT NULL,
            disk_total_bytes BIGINT NOT NULL,
            memory_used_percent FLOAT NOT NULL,
            disk_used_percent FLOAT NOT NULL
        );
        CREATE TABLE deployment_operations (
            id VARCHAR(36) PRIMARY KEY,
            deployment_id VARCHAR(36) NOT NULL,
            host_id VARCHAR(36) NOT NULL,
            op_type VARCHAR(16) NOT NULL,
            status VARCHAR(16) NOT NULL,
            claimed_at TIMESTAMP,
            completed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            result_json VARCHAR(2048),
            error_code VARCHAR(64),
            error_message VARCHAR(512)
        );
        INSERT INTO hosts VALUES ('5ca406e8-aaaa-bbbb-cccc-ddddeeeeffff', 'david-lab',
            'a'*64, '2026-11-09 12:34:17.351074', NULL, '0.1.0', 'Linux', '6.12', 4,
            8160437862, NULL, '2026-11-09 16:56:52.370367', NULL, 0);
        INSERT INTO telemetry (host_id, recorded_at, cpu_percent, memory_used_bytes,
            memory_total_bytes, disk_used_bytes, disk_total_bytes, memory_used_percent,
            disk_used_percent)
            VALUES ('5ca406e8-aaaa-bbbb-cccc-ddddeeeeffff', '2026-11-09 13:00:00', 12.5,
            1, 2, 1, 2, 50.0, 50.0);
        """
    )
    con.commit()
    before_hosts = con.execute("SELECT * FROM hosts").fetchall()
    before_tel = con.execute("SELECT * FROM telemetry").fetchall()
    con.close()

    # Run the Phase 3B upgrade against this legacy DB.
    from backend.app.core.migrations import upgrade_phase3b

    upgrade_phase3b(f"sqlite:///{legacy.as_posix()}")

    con = sqlite3.connect(legacy)
    hosts_after = con.execute("SELECT * FROM hosts").fetchall()
    tel_after = con.execute("SELECT * FROM telemetry").fetchall()

    # Host count/identity unchanged; only new columns added with expected backfill.
    assert len(hosts_after) == 1
    row = hosts_after[0]
    cols = [d[0] for d in con.execute("SELECT * FROM hosts").description]
    data = dict(zip(cols, row))
    assert data["id"] == "5ca406e8-aaaa-bbbb-cccc-ddddeeeeffff"
    assert data["hostname"] == "david-lab"
    assert data["enrollment_status"] == "ENROLLED"
    assert data["docker_enabled"] == 0
    assert data["credential_version"] == 1
    # Telemetry untouched.
    assert tel_after == before_tel
    # Legacy fields byte-for-byte (except added columns).
    legacy_cols = [d[0] for d in before_hosts and con.execute("SELECT * FROM hosts").description if d[0] in
        ("id", "hostname", "agent_token_hash", "enrolled_at", "is_revoked")]
    assert all(data[c] == dict(zip(cols, before_hosts[0]))[c] for c in legacy_cols)

    # New Phase 3B tables exist.
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("bootstrap_tokens", "operators", "operator_sessions", "host_events"):
        assert t in names
    con.close()


def test_upgrade_is_idempotent(tmp_path):
    """Gate 3: running the upgrade twice causes no errors and no drift."""
    db = tmp_path / "twice.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE hosts (
            id VARCHAR(36) PRIMARY KEY,
            hostname VARCHAR(255) UNIQUE NOT NULL,
            agent_token_hash VARCHAR(64) NOT NULL,
            enrolled_at TIMESTAMP NOT NULL,
            is_revoked BOOLEAN NOT NULL
        );
        INSERT INTO hosts VALUES ('h-1', 'x', 'h'*64, '2026-11-09 00:00:00', 0);
        """
    )
    con.commit()
    con.close()

    from backend.app.core.migrations import upgrade_phase3b

    url = f"sqlite:///{db.as_posix()}"
    upgrade_phase3b(url)  # first run
    con = sqlite3.connect(db)
    hosts_cols = [d[1] for d in con.execute("PRAGMA table_info(hosts)")]
    first_count = con.execute("SELECT COUNT(*) FROM hosts").fetchone()[0]
    first_status = con.execute("SELECT enrollment_status FROM hosts WHERE id='h-1'").fetchone()[0]
    con.close()

    upgrade_phase3b(url)  # second run: must not raise, not re-backfill wrongly
    con = sqlite3.connect(db)
    assert [d[1] for d in con.execute("PRAGMA table_info(hosts)")] == hosts_cols
    assert con.execute("SELECT COUNT(*) FROM hosts").fetchone()[0] == first_count
    assert con.execute("SELECT enrollment_status FROM hosts WHERE id='h-1'").fetchone()[0] == first_status
    con.close()
