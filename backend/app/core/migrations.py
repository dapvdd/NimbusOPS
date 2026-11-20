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
from dataclasses import dataclass

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
    # Phase 5 (FR-03): latest docker inventory per host (replace-on-report).
    "inventory_snapshots": """
        CREATE TABLE IF NOT EXISTS inventory_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            host_id VARCHAR(36) NOT NULL UNIQUE,
            observed_at TIMESTAMP NOT NULL,
            received_at TIMESTAMP NOT NULL,
            containers_json TEXT NOT NULL DEFAULT '[]'
        )
    """,
}

_NEW_HOST_COLUMNS = {
    # §2.5: (name, DDL fragment for ALTER TABLE ADD COLUMN, backfill value)
    "enrollment_status": ("VARCHAR(16)", "'ENROLLED'"),
    "docker_enabled": ("BOOLEAN", "0"),
    "credential_version": ("INTEGER", "1"),
    # Task 5: rotation grace window (dual-hash check).
    "previous_token_hash": ("VARCHAR(64)", None),
    "previous_token_expires_at": ("TIMESTAMP", None),
    # Phase 4 (FR-19): environment grouping. Existing hosts are private.
    "environment": ("VARCHAR(16)", "'PRIVATE'"),
    # Sprint D3: agent-reported mode. No backfill — legacy = NULL = "not
    # reported" (never guessed from docker_enabled).
    "agent_mode": ("VARCHAR(16)", None),
}

_NEW_TOKEN_COLUMNS = {
    # Sprint D2: intent enforced at issue and consumption. Legacy rows are
    # 'enroll' (pre-sprint tokens were only usable for fresh enrollment).
    "intent": ("VARCHAR(16)", "'enroll'"),
}

_NEW_OP_COLUMNS = {
    # §2.6 claim-timeout support (claimed_at already exists from Phase 2)
    "timeout_at": ("TIMESTAMP", None),
    # RC2 F07: fencing counter; legacy rows start at 0 (never claimed).
    "claim_generation": ("INTEGER", "0"),
}

_INDEXES = {
    "ix_bootstrap_tokens_hostname": "CREATE INDEX IF NOT EXISTS ix_bootstrap_tokens_hostname ON bootstrap_tokens (hostname)",
    "ix_host_events_host": "CREATE INDEX IF NOT EXISTS ix_host_events_host ON host_events (host_id, at)",
    "ix_inventory_host": "CREATE UNIQUE INDEX IF NOT EXISTS ix_inventory_snapshots_host ON inventory_snapshots (host_id)",
}

# RC2 F07: at most one non-terminal operation per deployment. Created
# separately because a legacy DB may already contain duplicates produced by
# the RC1 race; in that case the index is skipped (fail-safe boot) and an
# operator must reconcile, rather than the migration aborting app startup.
_INFLIGHT_INDEX_DDL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ops_inflight_deployment "
    "ON deployment_operations (deployment_id) "
    "WHERE status IN ('QUEUED', 'RUNNING')"
)

# Sprint D2: at most one active bootstrap token per hostname. Same fail-safe
# rule as the in-flight index: a legacy DB with duplicate active tokens must
# not block startup — the service-level guard still applies per transaction.
_ACTIVE_TOKEN_INDEX_DDL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_bootstrap_tokens_active_hostname "
    "ON bootstrap_tokens (hostname) "
    "WHERE consumed_at IS NULL AND revoked_at IS NULL"
)


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
            for col, (ddl, default) in _NEW_OP_COLUMNS.items():
                if col not in op_cols:
                    conn.execute(text(f"ALTER TABLE deployment_operations ADD COLUMN {col} {ddl}"))
                    logger.info("migration: added deployment_operations.%s", col)
                if default is not None:
                    conn.execute(
                        text(
                            f"UPDATE deployment_operations SET {col} = {default} "
                            f"WHERE {col} IS NULL"
                        )
                    )

        # 3b. Sprint D2: bootstrap_tokens.intent (legacy backfills to 'enroll').
        if inspect(eng).has_table("bootstrap_tokens"):
            token_cols = {c["name"] for c in inspect(eng).get_columns("bootstrap_tokens")}
            for col, (ddl, default) in _NEW_TOKEN_COLUMNS.items():
                if col not in token_cols:
                    conn.execute(text(f"ALTER TABLE bootstrap_tokens ADD COLUMN {col} {ddl}"))
                    logger.info("migration: added bootstrap_tokens.%s", col)
                if default is not None:
                    conn.execute(
                        text(f"UPDATE bootstrap_tokens SET {col} = {default} WHERE {col} IS NULL")
                    )

        # 4. Indexes.
        for name, ddl in _INDEXES.items():
            conn.execute(text(ddl))

        # 4b. RC2 F07 single-in-flight guard. Skip (never abort startup) when a
        # legacy database still holds duplicate in-flight rows.
        if inspect(eng).has_table("deployment_operations"):
            try:
                conn.execute(text(_INFLIGHT_INDEX_DDL))
            except Exception:  # noqa: BLE001 - duplicate legacy data must not block boot
                logger.warning(
                    "migration: ux_ops_inflight_deployment not created; "
                    "deployment_operations still holds duplicate in-flight rows "
                    "(operator reconciliation required)"
                )

        # 4c. Sprint D2 one-active-token guard. Same fail-safe rule: legacy
        # duplicates warn and skip instead of aborting startup.
        if inspect(eng).has_table("bootstrap_tokens"):
            try:
                conn.execute(text(_ACTIVE_TOKEN_INDEX_DDL))
            except Exception:  # noqa: BLE001 - duplicate legacy data must not block boot
                logger.warning(
                    "migration: ux_bootstrap_tokens_active_hostname not created; "
                    "bootstrap_tokens still holds duplicate active tokens for a "
                    "hostname (operator reconciliation required)"
                )

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
                    f"INSERT INTO {MIGRATION_MARKER_TABLE} (applied_at, revision) VALUES (CURRENT_TIMESTAMP, '0002_phase3b')"
                )
            )
            logger.info("migration: 0002_phase3b recorded")

    logger.info("migration: phase3b upgrade complete (idempotent)")


# ------------------------------------------------------ Sprint 5 (§4, §15)
#
# Additive zero-touch provisioning schema. Same mechanism as Phase 3B: raw SQL
# DDL (not ORM metadata) so a legacy DB converges to the §4 shape without
# importing the models. Additive-only, idempotent (every step checks before it
# alters), no renames, no deletes, no row mutation. All provisioning FKs use
# ON DELETE RESTRICT (§4): provisioning records are never cascade-deleted with
# hosts. Column contracts mirror backend/app/models/provisioning.py exactly:
# UUID text PKs, integer-millisecond UTC timestamps, booleans 0/1, hashes as
# fixed 64-hex strings, JSON as canonical text, bounded text enums via CHECK.

SPRINT5_MARKER_TABLE = "sprint5_migration_marker"

_S5_TABLES = {
    # §15.3: global machine/installation ownership root.
    "provisioning_machines": """
        CREATE TABLE IF NOT EXISTS provisioning_machines (
            id VARCHAR(36) PRIMARY KEY,
            machine_binding_hash VARCHAR(64) NOT NULL UNIQUE,
            installation_id VARCHAR(36) UNIQUE,
            binding_revision INTEGER NOT NULL DEFAULT 1
        )
    """,
    # §4: provider connection configuration mirror (nonsecret metadata only).
    "provisioning_connections": """
        CREATE TABLE IF NOT EXISTS provisioning_connections (
            id VARCHAR(36) PRIMARY KEY,
            provider VARCHAR(16) NOT NULL,
            display_name VARCHAR(255) NOT NULL,
            config_revision INTEGER NOT NULL DEFAULT 1,
            policy_hash VARCHAR(64) NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT 0,
            CHECK (provider IN ('AZURE_VM', 'GENERIC_LINUX', 'LOCAL_WINDOWS'))
        )
    """,
            # §15.3 targets FKs are IMMEDIATE (a dangling mapping insert must
            # fail at statement time); child tables defer to COMMIT.
            "provisioning_targets": """
        CREATE TABLE IF NOT EXISTS provisioning_targets (
            id VARCHAR(36) PRIMARY KEY,
            connection_id VARCHAR(36) NOT NULL REFERENCES provisioning_connections(id) ON DELETE RESTRICT,
            canonical_key VARCHAR(512) NOT NULL UNIQUE,
            observed_identity_hash VARCHAR(64),
            host_id VARCHAR(36) UNIQUE REFERENCES hosts(id) ON DELETE RESTRICT,
            machine_id VARCHAR(36) REFERENCES provisioning_machines(id) ON DELETE RESTRICT,
            mapping_revision INTEGER NOT NULL DEFAULT 0,
            mapping_status VARCHAR(32) NOT NULL DEFAULT 'UNMAPPED',
            discovered_at INTEGER NOT NULL DEFAULT 0,
            UNIQUE (connection_id, canonical_key),
            CHECK (mapping_status IN ('UNMAPPED', 'PENDING_MAPPING', 'MAPPED', 'IDENTITY_MAPPING_REQUIRED'))
        )
    """,
    # §4: reviewed plan fingerprint; consumable exactly once by one job.
    # consumed_by_job_id is a logical reference (no DB FK; D2 verifies it).
    "provisioning_validations": """
        CREATE TABLE IF NOT EXISTS provisioning_validations (
            id VARCHAR(36) PRIMARY KEY,
            target_id VARCHAR(36) NOT NULL REFERENCES provisioning_targets(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            actor_id VARCHAR(36) NOT NULL REFERENCES operators(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            plan_json TEXT NOT NULL,
            plan_hash VARCHAR(64) NOT NULL,
            config_revision INTEGER NOT NULL,
            mapping_revision INTEGER NOT NULL,
            observed_identity_hash VARCHAR(64) NOT NULL,
            created_at INTEGER NOT NULL DEFAULT 0,
            expires_at INTEGER NOT NULL,
            consumed_by_job_id VARCHAR(36) UNIQUE,
            expected_revocation_revision INTEGER NOT NULL DEFAULT 0,
            CHECK (expected_revocation_revision >= 0)
        )
    """,
    # §4: durable seven-state job (§3). Terminal iff completed_at is set.
    "provisioning_jobs": """
        CREATE TABLE IF NOT EXISTS provisioning_jobs (
            id VARCHAR(36) PRIMARY KEY,
            target_id VARCHAR(36) NOT NULL REFERENCES provisioning_targets(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            operation VARCHAR(16) NOT NULL,
            expected_host_id VARCHAR(36) REFERENCES hosts(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            validation_id VARCHAR(36) NOT NULL UNIQUE REFERENCES provisioning_validations(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            requester_id VARCHAR(36) NOT NULL REFERENCES operators(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            approval_hash VARCHAR(64) NOT NULL,
            approved_at INTEGER NOT NULL DEFAULT 0,
            approval_expires_at INTEGER NOT NULL,
            plan_json TEXT NOT NULL,
            state VARCHAR(16) NOT NULL DEFAULT 'PENDING',
            revision INTEGER NOT NULL DEFAULT 0,
            step VARCHAR(64) NOT NULL DEFAULT 'REVALIDATE',
            deadline_at INTEGER NOT NULL,
            cancel_requested_at INTEGER,
            reconciliation_required BOOLEAN NOT NULL DEFAULT 0,
            dispatch_blocked BOOLEAN NOT NULL DEFAULT 0,
            reason_code VARCHAR(64),
            next_check_at INTEGER,
            lease_owner VARCHAR(128),
            lease_until INTEGER,
            lease_generation INTEGER NOT NULL DEFAULT 0,
            retry_of_job_id VARCHAR(36) REFERENCES provisioning_jobs(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            created_at INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT 0,
            completed_at INTEGER,
            CHECK (state IN ('PENDING', 'VALIDATING', 'RUNNING', 'VERIFYING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
            CHECK (operation IN ('INSTALL', 'REENROLL', 'ROTATE', 'RESTART', 'DIAGNOSE', 'UPGRADE')),
            CHECK (revision >= 0),
            CHECK (lease_generation >= 0)
        )
    """,
    # §4: idempotency reservation; retained as long as the job.
    "provisioning_requests": """
        CREATE TABLE IF NOT EXISTS provisioning_requests (
            actor_id VARCHAR(36) NOT NULL,
            route_scope VARCHAR(64) NOT NULL,
            idempotency_key VARCHAR(128) NOT NULL,
            request_hash VARCHAR(64) NOT NULL,
            job_id VARCHAR(36) NOT NULL REFERENCES provisioning_jobs(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            PRIMARY KEY (actor_id, route_scope, idempotency_key)
        )
    """,
    # §4: target ownership; row and generation survive release (§5).
    "provisioning_ownership": """
        CREATE TABLE IF NOT EXISTS provisioning_ownership (
            target_id VARCHAR(36) PRIMARY KEY REFERENCES provisioning_targets(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            host_id VARCHAR(36) UNIQUE REFERENCES hosts(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            owner_job_id VARCHAR(36) NOT NULL UNIQUE REFERENCES provisioning_jobs(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            generation INTEGER NOT NULL DEFAULT 1,
            disposition VARCHAR(16) NOT NULL DEFAULT 'HELD',
            acquired_at INTEGER NOT NULL DEFAULT 0,
            released_at INTEGER,
            CHECK (generation >= 1),
            CHECK (disposition IN ('HELD', 'RECONCILING', 'RELEASED'))
        )
    """,
    # §4 §15.1: per-step attempt; ordinal 1..3; admission gate.
    "provisioning_attempts": """
        CREATE TABLE IF NOT EXISTS provisioning_attempts (
            id VARCHAR(36) PRIMARY KEY,
            job_id VARCHAR(36) NOT NULL REFERENCES provisioning_jobs(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            step_key VARCHAR(64) NOT NULL,
            ordinal INTEGER NOT NULL,
            dispatch_id VARCHAR(36) NOT NULL UNIQUE,
            ownership_generation INTEGER NOT NULL DEFAULT 1,
            intent_hash VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'INTENT',
            provider_handle VARCHAR(512),
            provider_receipt_json TEXT,
            started_at INTEGER NOT NULL DEFAULT 0,
            deadline_at INTEGER NOT NULL DEFAULT 0,
            next_attempt_at INTEGER,
            finished_at INTEGER,
            error_code VARCHAR(64),
            admission_state VARCHAR(16) NOT NULL DEFAULT 'OPEN',
            closed_at INTEGER,
            closure_reason VARCHAR(64),
            UNIQUE (job_id, step_key, ordinal),
            CHECK (ordinal IN (1, 2, 3)),
            CHECK (admission_state IN ('OPEN', 'ADMITTED', 'CLOSED'))
        )
    """,
    # §4: append-only job audit log; PK(job_id, sequence); sequence >= 1.
    "provisioning_events": """
        CREATE TABLE IF NOT EXISTS provisioning_events (
            job_id VARCHAR(36) NOT NULL REFERENCES provisioning_jobs(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            sequence INTEGER NOT NULL,
            at INTEGER NOT NULL,
            actor_kind VARCHAR(16) NOT NULL,
            actor_id VARCHAR(64) NOT NULL,
            code VARCHAR(32) NOT NULL,
            state VARCHAR(16),
            step VARCHAR(64),
            safe_detail_json TEXT,
            PRIMARY KEY (job_id, sequence),
            CHECK (sequence >= 1)
        )
    """,
    # §15.2: one-time provisioning token (hash only, never plaintext).
    "provisioning_grants": """
        CREATE TABLE IF NOT EXISTS provisioning_grants (
            id VARCHAR(36) PRIMARY KEY,
            job_id VARCHAR(36) NOT NULL REFERENCES provisioning_jobs(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            dispatch_id VARCHAR(36) NOT NULL REFERENCES provisioning_jobs(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            target_id VARCHAR(36) NOT NULL REFERENCES provisioning_targets(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            expected_host_id VARCHAR(36) REFERENCES hosts(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            intent VARCHAR(32) NOT NULL,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            expires_at INTEGER NOT NULL,
            consumed_at INTEGER,
            candidate_hash VARCHAR(64),
            result_host_id VARCHAR(36) REFERENCES hosts(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            result_credential_version INTEGER,
            revoked_at INTEGER,
            expected_revocation_revision INTEGER NOT NULL DEFAULT 0,
            CHECK (expected_revocation_revision >= 0)
        )
    """,
    # §15.2: durable credential commit audit (not secret escrow).
    "provisioning_credential_commits": """
        CREATE TABLE IF NOT EXISTS provisioning_credential_commits (
            id VARCHAR(36) PRIMARY KEY,
            job_id VARCHAR(36) NOT NULL REFERENCES provisioning_jobs(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            grant_id VARCHAR(36) NOT NULL UNIQUE REFERENCES provisioning_grants(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            host_id VARCHAR(36) NOT NULL REFERENCES hosts(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            previous_version INTEGER,
            committed_version INTEGER NOT NULL,
            candidate_hash VARCHAR(64),
            committed_at INTEGER NOT NULL DEFAULT 0,
            expected_revocation_revision INTEGER NOT NULL DEFAULT 0,
            UNIQUE (host_id, committed_version),
            CHECK (committed_version >= 1),
            CHECK (expected_revocation_revision >= 0)
        )
    """,
    # §15.3: per-attempt challenge; nonce consumed on first valid response.
    "provisioning_challenges": """
        CREATE TABLE IF NOT EXISTS provisioning_challenges (
            id VARCHAR(36) PRIMARY KEY,
            job_id VARCHAR(36) NOT NULL REFERENCES provisioning_jobs(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            host_id VARCHAR(36) NOT NULL REFERENCES hosts(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            credential_version INTEGER NOT NULL,
            runtime_instance_id VARCHAR(256),
            nonce_hash VARCHAR(64) NOT NULL UNIQUE,
            activation_sequence INTEGER NOT NULL DEFAULT 0,
            expires_at INTEGER NOT NULL,
            consumed_at INTEGER
        )
    """,
    # §15.3: agent identity proof; UUID text PK (rowid-free so the PK shows in
    # PRAGMA index_list as origin 'pk'); composite (job, kind, instance, seq) unique.
    "provisioning_receipts": """
        CREATE TABLE IF NOT EXISTS provisioning_receipts (
            id VARCHAR(36) PRIMARY KEY,
            job_id VARCHAR(36) NOT NULL REFERENCES provisioning_jobs(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            host_id VARCHAR(36) NOT NULL REFERENCES hosts(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            kind VARCHAR(16) NOT NULL,
            credential_version INTEGER NOT NULL,
            matched_slot VARCHAR(16) NOT NULL,
            runtime_instance_id VARCHAR(256),
            challenge_id VARCHAR(36) REFERENCES provisioning_challenges(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            sample_sequence INTEGER NOT NULL DEFAULT 0,
            received_at INTEGER NOT NULL DEFAULT 0,
            payload_hash VARCHAR(64),
            safe_metadata_json TEXT,
            UNIQUE (job_id, kind, runtime_instance_id, sample_sequence),
            CHECK (kind IN ('HEARTBEAT', 'TELEMETRY')),
            CHECK (matched_slot IN ('CURRENT', 'GRACE'))
        )
    """,
}

# §4 §107: required secondary indexes.
_S5_INDEXES = {
    "ix_jobs_dispatch": "CREATE INDEX IF NOT EXISTS ix_jobs_dispatch ON provisioning_jobs (state, next_check_at, lease_until)",
    "ix_jobs_target_created": "CREATE INDEX IF NOT EXISTS ix_jobs_target_created ON provisioning_jobs (target_id, created_at, id)",
    "ix_events_job_sequence": "CREATE INDEX IF NOT EXISTS ix_events_job_sequence ON provisioning_events (job_id, sequence)",
    "ix_attempts_job_status": "CREATE INDEX IF NOT EXISTS ix_attempts_job_status ON provisioning_attempts (job_id, status)",
    "ix_receipts_job_id": "CREATE INDEX IF NOT EXISTS ix_receipts_job_id ON provisioning_receipts (job_id, kind, runtime_instance_id, sample_sequence)",
    "ix_grants_job_expires": "CREATE INDEX IF NOT EXISTS ix_grants_job_expires ON provisioning_grants (job_id, expires_at)",
}

# §15.2: hosts.revocation_revision (DDL fragment, backfill value). NOT NULL is
# legal with a constant DEFAULT on ADD COLUMN; PRAGMA table_info must report
# notnull=1 (§4 column contract).
_S5_HOST_COLUMNS = {
    "revocation_revision": ("INTEGER NOT NULL", "0"),
}


def run_sprint5_migrations(database_url: str | None = None) -> None:
    """Bring a database (fresh or legacy) to the Sprint 5 §4 shape. Idempotent.

    Additive-only: creates the 13 provisioning tables plus required secondary
    indexes when missing, adds hosts.revocation_revision with backfill 0, and
    records the 0003_sprint5 marker once. Never deletes rows or columns; the
    write transaction runs under BEGIN IMMEDIATE (§4 §111 hygiene). Re-running
    is a no-op.
    """
    eng = _engine_for(database_url) if database_url else None
    if eng is None:
        from ..core.db import engine as app_engine

        eng = app_engine

    insp = inspect(eng)
    tables = set(insp.get_table_names())

    with eng.begin() as conn:
        # SQLite writes run under BEGIN IMMEDIATE so concurrent workers/API
        # processes serialize instead of failing with a deferred-lock error.
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            # 1. New tables.
            for name, ddl in _S5_TABLES.items():
                if name not in tables:
                    conn.execute(text(ddl))
                    logger.info("migration: created table %s", name)

            # 2. Required secondary indexes.
            for name, ddl in _S5_INDEXES.items():
                conn.execute(text(ddl))

            # 3. hosts.revocation_revision (additive, backfill 0).
            if "hosts" in tables or inspect(eng).has_table("hosts"):
                host_cols = {c["name"] for c in inspect(eng).get_columns("hosts")}
                for col, (ddl, default) in _S5_HOST_COLUMNS.items():
                    if col not in host_cols:
                        # DEFAULT is required by SQLite for a NOT NULL ADD COLUMN;
                        # it also backfills existing rows to 0 (§15.2).
                        conn.execute(text(f"ALTER TABLE hosts ADD COLUMN {col} {ddl} DEFAULT {default}"))
                        logger.info("migration: added hosts.%s", col)
                    if default is not None:
                        conn.execute(
                            text(f"UPDATE hosts SET {col} = {default} WHERE {col} IS NULL")
                        )

            # 4. Version marker (records that the upgrade ran; not a gate).
            conn.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {SPRINT5_MARKER_TABLE} ("
                    "applied_at TIMESTAMP NOT NULL, revision VARCHAR(64) NOT NULL)"
                )
            )
            existing = conn.execute(
                text(f"SELECT COUNT(*) FROM {SPRINT5_MARKER_TABLE} WHERE revision = '0003_sprint5'")
            ).scalar_one()
            if existing == 0:
                conn.execute(
                    text(
                        f"INSERT INTO {SPRINT5_MARKER_TABLE} (applied_at, revision)"
                        " VALUES (CURRENT_TIMESTAMP, '0003_sprint5')"
                    )
                )
                logger.info("migration: 0003_sprint5 recorded")
        except Exception:
            conn.exec_driver_sql("ROLLBACK")
            raise
        else:
            conn.exec_driver_sql("COMMIT")

    logger.info("migration: sprint5 upgrade complete (idempotent)")


# ------------------------------------------------- Sprint 5 readiness (§4 §109)


@dataclass(frozen=True)
class ReadinessEntry:
    """One typed readiness finding (§4: fail-closed, remediation-bearing)."""

    code: str
    blocking: bool
    detail: str = ""


@dataclass(frozen=True)
class ReadinessReport:
    """Aggregated provisioning schema readiness; `.ok` is False iff blocking."""

    entries: tuple[ReadinessEntry, ...]

    @property
    def ok(self) -> bool:
        return not any(entry.blocking for entry in self.entries)


def _readiness_engine(database_url: str | None) -> Engine:
    return _engine_for(database_url) if database_url else None


def assert_provisioning_readiness(database_url: str | None = None) -> ReadinessReport:
    """Verify the §4 provisioning schema guards without mutating anything.

    Fail-closed (§4 §109): a missing required unique index or a duplicate
    collision yields a blocking entry; colliding rows are reported, never
    deleted. The synchronous=FULL verification is informational and never
    blocks on its own. Read-only: only SELECT/PRAGMA statements run.
    """
    eng = _readiness_engine(database_url)
    if eng is None:
        from ..core.db import engine as app_engine

        eng = app_engine

    entries: list[ReadinessEntry] = []
    insp = inspect(eng)
    tables = set(insp.get_table_names())

    with eng.connect() as conn:
        # 1. Required unique indexes (§4 §107 / REQUIRED_INDEXES contract).
        # A unique constraint appears either as a named index (CREATE UNIQUE
        # INDEX / Index(...) in table_args) or as an unnamed SQLite autoindex
        # backing a column/table UNIQUE/PK constraint; both satisfy the guard.
        # Match by indexed COLUMN SET, not by name: any unique index whose
        # column set covers the required single column satisfies it.
        for table, col in (
            ("provisioning_validations", "consumed_by_job_id"),
            ("provisioning_jobs", "validation_id"),
            ("provisioning_grants", "token_hash"),
            ("provisioning_credential_commits", "grant_id"),
            ("provisioning_challenges", "nonce_hash"),
        ):
            if table not in tables:
                entries.append(
                    ReadinessEntry(
                        code=f"missing_unique_index:{table}.{col}",
                        blocking=True,
                        detail="table absent",
                    )
                )
                continue
            unique_cols = [
                [r[2] for r in conn.exec_driver_sql(f"PRAGMA index_info({row[1]})")]
                for row in conn.exec_driver_sql(f"PRAGMA index_list({table})")
                if row[2]
            ]
            if not any(col in cols for cols in unique_cols):
                entries.append(
                    ReadinessEntry(
                        code=f"missing_unique_index:{table}.{col}",
                        blocking=True,
                        detail="required unique index absent; create it before enabling provisioning",
                    )
                )

        # 2. Required unique indexes beyond the single-column guards:
        #    provisioning_targets.canonical_key (§4 line 95 UNIQUE) — rebuilt
        #    legacy tables may lose it; its absence must block.
        if "provisioning_targets" in tables:
            t_unique_cols = [
                [r[2] for r in conn.exec_driver_sql(f"PRAGMA index_info({row[1]})")]
                for row in conn.exec_driver_sql("PRAGMA index_list(provisioning_targets)")
                if row[2]
            ]
            if not any("canonical_key" in cols for cols in t_unique_cols):
                entries.append(
                    ReadinessEntry(
                        code="missing_unique_index:provisioning_targets.canonical_key",
                        blocking=True,
                        detail="required unique index on provisioning_targets.canonical_key absent",
                    )
                )
            # Duplicate collisions for unique keys — fail closed, never delete.
            #    Checked regardless of index presence so a dropped index with
            #    duplicate data is still reported (defense in depth).
            dup_rows = conn.execute(
                text(
                    "SELECT canonical_key, COUNT(*) AS n FROM provisioning_targets"
                    " GROUP BY canonical_key HAVING COUNT(*) > 1"
                )
            ).fetchall()
            for key, n in dup_rows:
                entries.append(
                    ReadinessEntry(
                        code=f"duplicate_collision:provisioning_targets.canonical_key:{key}",
                        blocking=True,
                        detail=f"{n} rows share canonical_key; operator must reconcile (rows are never deleted)",
                    )
                )

        # 3. synchronous=FULL verification (§4 §111): informational only.
        try:
            synchronous = conn.exec_driver_sql("PRAGMA synchronous").scalar()
            if synchronous == 2:  # SQLITE_SYNC_FULL
                entries.append(
                    ReadinessEntry(
                        code="synchronous_full_verified",
                        blocking=False,
                        detail="PRAGMA synchronous=FULL verified",
                    )
                )
            else:
                entries.append(
                    ReadinessEntry(
                        code=f"synchronous_not_full:{synchronous}",
                        blocking=False,
                        detail="PRAGMA synchronous is not FULL; set it before enabling provisioning",
                    )
                )
        except Exception:  # noqa: BLE001 - non-SQLite engines report info-only
            entries.append(
                ReadinessEntry(
                    code="synchronous_unverified",
                    blocking=False,
                    detail="PRAGMA synchronous unavailable on this engine",
                )
            )

        # 4. Marker presence (informational; the marker is not a gate).
        if SPRINT5_MARKER_TABLE in tables:
            entries.append(
                ReadinessEntry(
                    code="marker_present",
                    blocking=False,
                    detail="sprint5_migration_marker row present",
                )
            )
        else:
            entries.append(
                ReadinessEntry(
                    code="marker_absent",
                    blocking=False,
                    detail="run_migrations has not recorded 0003_sprint5",
                )
            )

    return ReadinessReport(entries=tuple(entries))

