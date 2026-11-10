"""Phase 3B schema migration (additive-only).

Implements docs/PHASE3B_MIGRATION_PLAN.md §2 and §3.2 (the hand-written,
idempotent upgrade). Alembic is introduced in Phase 3B per decision O7, but
this module is the mechanism the app actually runs at startup — Alembic's
env wires the same metadata, and this function remains the guard that makes
legacy DBs converge to the same shape on every boot.

Safety properties (from the migration plan):
- Additive-only: new tables, new columns with constant defaults, backfill by
  UPDATE. No renames, no deletes, no type changes, no row deletion.
- Idempotent: every step checks before it alters; a version marker row
  records that the upgrade ran.
- DavidLab-safe: existing rows keep their id/credential; only the three new
  column values are written.
"""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("nimbusops.migrations")

MIGRATION_MARKER_TABLE = "phase3b_migration_marker"

_NEW_TABLES = {
    # §2.1 bootstrap tokens (single-use, hashed, scoped, auditable)
    "bootstrap_tokens": """
        CREATE TABLE IF NOT EXISTS bootstrap_tokens (
            id VARCHAR(36) PRIMARY KEY,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            hostname VARCHAR(255) NOT NULL,
            created_by VARCHAR(36),
            created_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            consumed_at TIMESTAMP,
            consumed_by VARCHAR(36),
            revoked_at TIMESTAMP
        )
    """,
    # §2.2 operators
    "operators": """
        CREATE TABLE IF NOT EXISTS operators (
            id VARCHAR(36) PRIMARY KEY,
            username VARCHAR(64) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(16) NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    """,
    # §2.3 operator sessions
    "operator_sessions": """
        CREATE TABLE IF NOT EXISTS operator_sessions (
            id VARCHAR(36) PRIMARY KEY,
            operator_id VARCHAR(36) NOT NULL,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            created_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            revoked_at TIMESTAMP
        )
    """,
    # §2.4 append-only host event audit
    "host_events": """
        CREATE TABLE IF NOT EXISTS host_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TIMESTAMP NOT NULL,
            host_id VARCHAR(36),
            event VARCHAR(32) NOT NULL,
            actor VARCHAR(64) NOT NULL,
            detail VARCHAR(512)
        )
    """,
}

_NEW_HOST_COLUMNS = {
    # §2.5: (name, DDL fragment for ALTER TABLE ADD COLUMN, backfill value)
    "enrollment_status": ("VARCHAR(16)", "'ENROLLED'"),
    "docker_enabled": ("BOOLEAN", "0"),
    "credential_version": ("INTEGER", "1"),
}

_NEW_OP_COLUMNS = {
    # §2.6 claim-timeout support (claimed_at already exists from Phase 2)
    "timeout_at": ("TIMESTAMP", None),
}

_INDEXES = {
    "ix_bootstrap_tokens_hostname": "CREATE INDEX IF NOT EXISTS ix_bootstrap_tokens_hostname ON bootstrap_tokens (hostname)",
    "ix_host_events_host": "CREATE INDEX IF NOT EXISTS ix_host_events_host ON host_events (host_id, at)",
}


def _engine_for(url: str) -> Engine:
    return create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})


def upgrade_phase3b(database_url: str | None = None) -> None:
    """Bring a database (fresh or legacy) to the Phase 3B shape. Idempotent.

    Runs inside the app lifespan on every boot; each step is a no-op when
    already applied. Uses raw SQL DDL (not ORM metadata) so it can upgrade a
    legacy DB that predates the current models without importing them.
    """
    eng = _engine_for(database_url) if database_url else None
    if eng is None:
        # Default: the application's configured engine (imported lazily so
        # tests that override NIMBUSOPS_DATABASE_URL before import still win).
        from ..core.db import engine as app_engine

        eng = app_engine

    insp = inspect(eng)
    tables = set(insp.get_table_names())

    with eng.begin() as conn:
        # 1. New tables.
        for name, ddl in _NEW_TABLES.items():
            if name not in tables:
                conn.execute(text(ddl))
                logger.info("migration: created table %s", name)

        # 2. New host columns (add if missing, backfill NULLs with defaults).
        if "hosts" in tables or inspect(eng).has_table("hosts"):
            host_cols = {c["name"] for c in inspect(eng).get_columns("hosts")}
            for col, (ddl, default) in _NEW_HOST_COLUMNS.items():
                if col not in host_cols:
                    conn.execute(text(f"ALTER TABLE hosts ADD COLUMN {col} {ddl}"))
                    logger.info("migration: added hosts.%s", col)
                if default is not None:
                    conn.execute(
                        text(f"UPDATE hosts SET {col} = {default} WHERE {col} IS NULL")
                    )

        # 3. deployment_operations.timeout_at (no backfill: legacy ops have no claim deadline).
        if inspect(eng).has_table("deployment_operations"):
            op_cols = {c["name"] for c in inspect(eng).get_columns("deployment_operations")}
            for col, (ddl, _default) in _NEW_OP_COLUMNS.items():
                if col not in op_cols:
                    conn.execute(text(f"ALTER TABLE deployment_operations ADD COLUMN {col} {ddl}"))
                    logger.info("migration: added deployment_operations.%s", col)

        # 4. Indexes.
        for name, ddl in _INDEXES.items():
            conn.execute(text(ddl))

        # 5. Version marker (records that the upgrade ran; not a gate).
        conn.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {MIGRATION_MARKER_TABLE} ("
                "applied_at TIMESTAMP NOT NULL, revision VARCHAR(64) NOT NULL)"
            )
        )
        existing = conn.execute(
            text(f"SELECT COUNT(*) FROM {MIGRATION_MARKER_TABLE} WHERE revision = '0002_phase3b'")
        ).scalar_one()
        if existing == 0:
            conn.execute(
                text(
                    f"INSERT INTO {MIGRATION_MARKER_TABLE} (applied_at, revision) "
                    "(CURRENT_TIMESTAMP, '0002_phase3b')" if False else
                    f"INSERT INTO {MIGRATION_MARKER_TABLE} (applied_at, revision) VALUES (CURRENT_TIMESTAMP, '0002_phase3b')"
                )
            )
            logger.info("migration: 0002_phase3b recorded")

    logger.info("migration: phase3b upgrade complete (idempotent)")
