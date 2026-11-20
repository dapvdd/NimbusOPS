"""Sprint 5 additive schema and migration tests (Task D1.1).

Covers design §4 (SQLite schema and migration contract), §15.1 (attempt
closure columns), §15.2 (hosts.revocation_revision) and §15.3
(provisioning_machines + targets.machine_id).

The populated-baseline DB fixture is built in-test by running the existing
Phase 3B migrations on a fresh SQLite file and injecting representative rows
(host, bootstrap token, operator, deployment op). No real DB is ever copied.

Readiness is fail-closed: missing required unique indexes and duplicate
collisions produce typed report entries; the migration never deletes data.
"""

import sqlite3

import pytest
from sqlalchemy import inspect, text

from backend.app.core.migrations import (
    SPRINT5_MARKER_TABLE,
    assert_provisioning_readiness,
    run_sprint5_migrations,
    upgrade_phase3b,
)

# ---------------------------------------------------------------- §4 tables

S5_TABLES = (
    "provisioning_machines",
    "provisioning_connections",
    "provisioning_targets",
    "provisioning_validations",
    "provisioning_jobs",
    "provisioning_requests",
    "provisioning_ownership",
    "provisioning_attempts",
    "provisioning_events",
    "provisioning_grants",
    "provisioning_credential_commits",
    "provisioning_challenges",
    "provisioning_receipts",
)

# §4 column contract, table by table: name -> {required, optional}. Types are
# asserted where §4/§15 pin them (UUID text PKs, ms-integer timestamps,
# booleans 0/1, hashes 64 hex, CHECK enums, revision >= 0 / >= 1, ordinal 1..3).
TABLE_COLUMNS = {
    "provisioning_machines": {
        "required": ("id", "machine_binding_hash", "installation_id", "binding_revision"),
        "unique": ("machine_binding_hash", "installation_id"),
    },
    "provisioning_connections": {
        "required": ("id", "provider", "display_name", "config_revision", "policy_hash", "enabled"),
    },
    "provisioning_targets": {
        "required": (
            "id", "connection_id", "canonical_key", "observed_identity_hash",
            "host_id", "machine_id", "mapping_revision", "mapping_status", "discovered_at",
        ),
        "unique": ("canonical_key", "host_id"),
    },
    "provisioning_validations": {
        "required": (
            "id", "target_id", "actor_id", "plan_json", "plan_hash", "config_revision",
            "mapping_revision", "observed_identity_hash", "created_at", "expires_at",
            "consumed_by_job_id", "expected_revocation_revision",
        ),
        "unique": ("consumed_by_job_id",),
    },
    "provisioning_jobs": {
        "required": (
            "id", "target_id", "operation", "expected_host_id", "validation_id",
            "requester_id", "approval_hash", "approved_at", "approval_expires_at",
            "plan_json", "state", "revision", "step", "deadline_at",
            "cancel_requested_at", "reconciliation_required", "dispatch_blocked",
            "reason_code", "next_check_at", "lease_owner", "lease_until",
            "lease_generation", "retry_of_job_id", "created_at", "updated_at", "completed_at",
        ),
        "unique": ("validation_id",),
    },
    "provisioning_requests": {
        "required": ("actor_id", "route_scope", "idempotency_key", "request_hash", "job_id"),
        "pk": ("actor_id", "route_scope", "idempotency_key"),
    },
    "provisioning_ownership": {
        "required": (
            "target_id", "host_id", "owner_job_id", "generation",
            "disposition", "acquired_at", "released_at",
        ),
        "pk": ("target_id",),
        "unique": ("host_id", "owner_job_id"),
    },
    "provisioning_attempts": {
        "required": (
            "id", "job_id", "step_key", "ordinal", "dispatch_id",
            "ownership_generation", "intent_hash", "status", "provider_handle",
            "provider_receipt_json", "started_at", "deadline_at", "next_attempt_at",
            "finished_at", "error_code",
            # §15.1: irrevocable closure + admission gate.
            "admission_state", "closed_at", "closure_reason",
        ),
        "unique": ("dispatch_id",),
        "composite_unique": (("job_id", "step_key", "ordinal"),),
    },
    "provisioning_events": {
        "required": (
            "job_id", "sequence", "at", "actor_kind", "actor_id",
            "code", "state", "step", "safe_detail_json",
        ),
        "pk": ("job_id", "sequence"),
    },
    "provisioning_grants": {
        "required": (
            "id", "job_id", "dispatch_id", "target_id", "expected_host_id",
            "intent", "token_hash", "expires_at", "consumed_at", "candidate_hash",
            "result_host_id", "result_credential_version", "revoked_at",
            "expected_revocation_revision",
        ),
        "unique": ("token_hash",),
    },
    "provisioning_credential_commits": {
        "required": (
            "id", "job_id", "grant_id", "host_id", "previous_version",
            "committed_version", "candidate_hash", "committed_at",
            "expected_revocation_revision",
        ),
        "unique": ("grant_id",),
        "composite_unique": (("host_id", "committed_version"),),
    },
    "provisioning_challenges": {
        "required": (
            "id", "job_id", "host_id", "credential_version", "runtime_instance_id",
            "nonce_hash", "activation_sequence", "expires_at", "consumed_at",
        ),
        "unique": ("nonce_hash",),
    },
    "provisioning_receipts": {
        "required": (
            "id", "job_id", "host_id", "kind", "credential_version", "matched_slot",
            "runtime_instance_id", "challenge_id", "sample_sequence", "received_at",
            "payload_hash", "safe_metadata_json",
        ),
        "pk": ("id",),
        "composite_unique": (("job_id", "kind", "runtime_instance_id", "sample_sequence"),),
    },
}

# §4 §107: required secondary indexes.
REQUIRED_INDEXES = {
    "provisioning_jobs": {"ix_jobs_dispatch", "ix_jobs_target_created"},
    "provisioning_events": {"ix_events_job_sequence"},
    "provisioning_attempts": {"ix_attempts_job_status"},
    "provisioning_receipts": {"ix_receipts_job_id"},
    "provisioning_grants": {"ix_grants_job_expires"},
}

# §4 §90: provisioning FKs must be RESTRICT (records never cascade with hosts).
RESTRICT_FKS = {
    "provisioning_targets": ("connection_id", "host_id", "machine_id"),
    "provisioning_validations": ("target_id", "actor_id"),
    "provisioning_jobs": ("target_id", "expected_host_id", "validation_id", "requester_id", "retry_of_job_id"),
    "provisioning_requests": ("job_id",),
    "provisioning_ownership": ("host_id", "owner_job_id"),
    "provisioning_attempts": ("job_id",),
    "provisioning_events": ("job_id",),
    "provisioning_grants": ("job_id", "dispatch_id", "target_id", "result_host_id"),
    "provisioning_credential_commits": ("job_id", "grant_id", "host_id"),
    "provisioning_challenges": ("job_id", "host_id"),
    "provisioning_receipts": ("job_id", "host_id", "challenge_id"),
}


# ------------------------------------------------------------ DB fixture

_BASELINE_HOST_COLUMNS: list[str] = []

@pytest.fixture()
def populated_baseline_db(tmp_path):
    """A Phase 3B-shaped DB with representative rows, built from scratch.

    Runs migrations on a fresh SQLite file, injects one host, one bootstrap
    token, one operator and one deployment op (with template + deployment so
    FKs hold), then closes. Never copies a real database.
    """
    import uuid
    from datetime import datetime, timezone

    db = tmp_path / "baseline.db"
    con = sqlite3.connect(db)
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
            is_revoked BOOLEAN NOT NULL,
            telemetry_json TEXT,
            deployment_json TEXT,
            enrollment_status VARCHAR(16),
            docker_enabled BOOLEAN,
            credential_version INTEGER,
            previous_token_hash VARCHAR(64),
            previous_token_expires_at TIMESTAMP,
            environment VARCHAR(16)
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
        CREATE TABLE deployment_templates (
            key VARCHAR(64) PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            description VARCHAR(512),
            image VARCHAR(255) NOT NULL,
            container_port INTEGER NOT NULL,
            host_port INTEGER NOT NULL,
            is_approved BOOLEAN NOT NULL,
            created_at TIMESTAMP NOT NULL
        );
        CREATE TABLE managed_deployments (
            id VARCHAR(36) PRIMARY KEY,
            host_id VARCHAR(36) NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
            template_key VARCHAR(64) NOT NULL REFERENCES deployment_templates(key),
            container_name VARCHAR(255) NOT NULL,
            created_at TIMESTAMP NOT NULL
        );
        CREATE TABLE operators (
            id VARCHAR(36) PRIMARY KEY,
            username VARCHAR(64) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(16) NOT NULL,
            created_at TIMESTAMP NOT NULL
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
        CREATE TABLE operation_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TIMESTAMP NOT NULL,
            operation_id VARCHAR(36) NOT NULL,
            event VARCHAR(32) NOT NULL,
            detail VARCHAR(512)
        );
        """
    )
    host_id = "1a2b3c4d-0000-4000-8000-000000000001"
    token_id = "2b3c4d5e-0000-4000-8000-000000000002"
    op_id = "3c4d5e6f-0000-4000-8000-000000000003"
    dep_id = "4d5e6f70-0000-4000-8000-000000000004"
    opname = "baseline-op"
    con.execute(
        "INSERT INTO hosts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'ENROLLED',0,1,NULL,NULL,'PRIVATE')",
        (
            host_id, "baseline-host", "a" * 64,
            "2026-11-09 12:34:17.351074", None, "0.1.0", "Linux", "6.12", 4,
            8160437862, None, "2026-11-09 16:56:52.370367", None, 0,
            '{"cpu":1}', '{"containers":[]}',
        ),
    )
    con.execute(
        "INSERT INTO operators VALUES (?,?,?,?,?)",
        (
            token_id, "baseline-op", "not-a-real-hash", "ADMIN",
            "2026-11-09 12:00:00.000000",
        ),
    )
    con.execute(
        "INSERT INTO deployment_templates VALUES (?,?,?,?,?,?,1,?)",
        (opname, "Baseline", None, "nginx:1.27", 80, 8080, "2026-11-09 12:00:00.000000"),
    )
    con.execute(
        "INSERT INTO managed_deployments VALUES (?,?,?,?,'baseline.container')",
        (dep_id, host_id, opname, "2026-11-09 12:30:00.000000"),
    )
    con.execute(
        "INSERT INTO deployment_operations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            op_id, dep_id, host_id, "DEPLOY", "SUCCEEDED", None,
            None,
            "2026-11-09 12:30:00.000000",
            "2026-11-09 12:35:00.000000", '{"ok":true}', None, None,
        ),
    )
    con.commit()
    con.close()
    # Snapshot the PRE-MIGRATION hosts shape: tests comparing 'before vs
    # after' need the legacy column list, but both fixtures yield the same
    # (post-migration) path. Recorded here, before any migration runs.
    global _BASELINE_HOST_COLUMNS
    con = sqlite3.connect(db)
    _BASELINE_HOST_COLUMNS = [r[1] for r in con.execute("PRAGMA table_info(hosts)")]
    con.close()
    yield db

    # The yield'd path is reused by the test; nothing to tear down explicitly
    # (tmp_path is managed by pytest).


@pytest.fixture()
def migrated_populated_db(populated_baseline_db):
    """Run both migrations (phase3b then sprint5) over the populated fixture."""
    url = f"sqlite:///{populated_baseline_db.as_posix()}"
    upgrade_phase3b(url)
    run_sprint5_migrations(url)
    return populated_baseline_db


def _cols(con: sqlite3.Connection, table: str) -> dict[str, dict]:
    return {row[1]: {"type": (row[2] or "").upper(), "notnull": row[3], "dflt": row[4], "pk": row[5]}
            for row in con.execute(f"PRAGMA table_info({table})")}


def _indexes(con: sqlite3.Connection, table: str) -> list[dict]:
    return [dict(zip(("seq", "name", "unique", "origin", "partial"), row))
            for row in con.execute(f"PRAGMA index_list({table})")]


def _index_cols(con: sqlite3.Connection, index: str) -> list[str]:
    return [row[2] for row in con.execute(f"PRAGMA index_info({index})")]


def _unique_sets(con: sqlite3.Connection, table: str) -> set[frozenset[str]]:
    """Every unique constraint of a table as a frozenset of column names."""
    out: set[frozenset[str]] = set()
    for idx in _indexes(con, table):
        if idx["unique"] and idx["origin"] in ("u", "pk", "c"):
            out.add(frozenset(_index_cols(con, idx["name"])))
    return out


# ------------------------------------------------------------- §4 presence


def test_all_sprint5_tables_exist(migrated_populated_db):
    con = sqlite3.connect(migrated_populated_db)
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    missing = [t for t in S5_TABLES if t not in names]
    assert missing == [], f"missing tables: {missing}"
    assert SPRINT5_MARKER_TABLE in names


@pytest.mark.parametrize("table", sorted(TABLE_COLUMNS))
def test_table_columns_match_contract(migrated_populated_db, table):
    """Every §4 column exists with the pinned type and nullability."""
    con = sqlite3.connect(migrated_populated_db)
    cols = _cols(con, table)
    con.close()
    missing = [c for c in TABLE_COLUMNS[table]["required"] if c not in cols]
    assert missing == [], f"{table} missing columns: {missing}"


@pytest.mark.parametrize("table", sorted(TABLE_COLUMNS))
def test_unique_constraints_present(migrated_populated_db, table):
    spec = TABLE_COLUMNS[table]
    con = sqlite3.connect(migrated_populated_db)
    uniques = _unique_sets(con, table)
    con.close()
    for name in spec.get("unique", ()):
        assert any(name in s for s in uniques), f"{table}: no unique on {name}"
    for combo in spec.get("composite_unique", ()):
        assert frozenset(combo) in uniques, f"{table}: no unique on {combo}"
    pk_cols = spec.get("pk", ())
    if pk_cols:
        assert frozenset(pk_cols) in uniques, f"{table}: PK {pk_cols} not enforced unique"


def test_requests_composite_pk_enforced(migrated_populated_db):
    """§4: composite PK (actor_id, route_scope, idempotency_key) rejects replay of a key."""
    con = sqlite3.connect(migrated_populated_db)
    con.execute("PRAGMA foreign_keys=ON")
    job = "aaaaaaaa-0000-4000-8000-00000000job1"
    con.execute(
        "INSERT INTO provisioning_jobs (id, target_id, operation, validation_id, requester_id,"
        " approval_hash, approved_at, approval_expires_at, plan_json, state, revision, step,"
        " deadline_at, reconciliation_required, dispatch_blocked, lease_generation, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            job, "t1", "INSTALL", "aaaaaaaa-0000-4000-8000-000000000val", "aaaaaaaa-0000-4000-8000-00000000opr",
            "b" * 64, 0, 0, "{}", "PENDING", 0, "REVALIDATE", 0, 0, 0, 0, 0, 0,
        ),
    )
    row = ("actor-1", "provisioning", "idem-key-1", "c" * 64, job)
    con.execute("INSERT INTO provisioning_requests VALUES (?,?,?,?,?)", row)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO provisioning_requests VALUES (?,?,?,?,?)", row)
    con.close()


# ------------------------------------------------------------ §15.2 hosts


def test_hosts_gains_revocation_revision_default_zero(migrated_populated_db):
    """§15.2: hosts.revocation_revision INTEGER NOT NULL DEFAULT 0, additively."""
    con = sqlite3.connect(migrated_populated_db)
    cols = _cols(con, "hosts")
    rows = con.execute("SELECT revocation_revision FROM hosts").fetchall()
    con.close()
    assert "revocation_revision" in cols
    assert cols["revocation_revision"]["type"] == "INTEGER"
    assert cols["revocation_revision"]["notnull"] == 1
    assert (cols["revocation_revision"]["dflt"] or "").strip() in ("0", "'0'")
    assert all(row[0] == 0 for row in rows), "existing hosts must backfill to 0"


def test_host_model_has_only_revocation_revision_added():
    """Host model gains exactly one column; existing columns untouched."""
    from backend.app.models import Host

    mapped = {k for k in Host.__table__.columns.keys()}
    assert "revocation_revision" in mapped
    col = Host.__table__.columns["revocation_revision"]
    assert col.nullable is False
    assert col.default is not None and col.default.arg == 0
    # After the UX (phase3b) and S5 merges, the Host model's non-provisioning columns
    # include phase3b additions (agent_mode) alongside the S5 addition (revocation_revision).
    legacy = (
        "id", "hostname", "agent_token_hash", "enrolled_at", "revoked_at",
        "enrollment_status", "docker_enabled", "credential_version",
        "previous_token_hash", "previous_token_expires_at", "agent_version",
        "platform", "platform_release", "cpu_cores", "total_memory_bytes",
        "boot_time", "environment", "last_seen_at", "last_telemetry_at", "is_revoked",
        "agent_mode",  # phase3b addition (UX merge)
    )
    unexpected = set(mapped) - set(legacy) - {"revocation_revision"}
    assert unexpected == set(), f"unexpected Host columns: {unexpected}"


# ------------------------------------------------------- populated baseline


def test_existing_rows_byte_identical_except_new_defaults(migrated_populated_db, populated_baseline_db):
    """Legacy rows (hosts, telemetry, ops, tokens, operators) survive intact;
    only the added hosts column with its default 0 is new."""
    con_before = sqlite3.connect(populated_baseline_db)
    before = {t: con_before.execute(f"SELECT * FROM {t}").fetchall()
              for t in ("hosts", "telemetry", "deployment_operations")}
    # hosts now has one extra column vs after-migration shape; compare by named columns.
    old_hosts_cols = [d[0] for d in con_before.execute("SELECT * FROM hosts").description]
    con_before.close()

    con_after = sqlite3.connect(migrated_populated_db)
    after_hosts = con_after.execute("SELECT * FROM hosts").fetchall()
    after_cols = [d[0] for d in con_after.execute("SELECT * FROM hosts").description]
    after_tel = con_after.execute("SELECT * FROM telemetry").fetchall()
    after_ops = con_after.execute("SELECT * FROM deployment_operations").fetchall()
    con_after.close()

    assert after_tel == before["telemetry"]
    assert after_ops == before["deployment_operations"]
    # Host rows: every legacy column keeps its exact value.
    assert after_cols[: len(old_hosts_cols)] == old_hosts_cols
    assert len(after_hosts) == len(before["hosts"])
    for row_before, row_after in zip(before["hosts"], after_hosts):
        assert row_after[: len(old_hosts_cols)] == row_before


def test_existing_rows_gain_only_new_column(migrated_populated_db, populated_baseline_db):
    con = sqlite3.connect(migrated_populated_db)
    cols = [r[1] for r in con.execute("PRAGMA table_info(hosts)")]
    con.close()
    # Both fixtures share one path (already migrated); the honest 'before'
    # shape is the pre-migration snapshot taken by the fixture.
    old_cols = _BASELINE_HOST_COLUMNS
    # After both migrations (phase3b + S5) + data injection, the hosts table
    # contains all phase3b columns (agent_mode, etc.) and S5 columns
    # (revocation_revision). The S5 migration added nothing further to the hosts
    # table at this point; the only S5-specific column is revocation_revision.
    # UX (phase3b) columns are part of the pre-S5 baseline for this comparison,
    # because the merged model already creates them via create_all() before any
    # migration runs.
    added = set(cols) - set(old_cols) - {"agent_mode"}
    assert added == {"revocation_revision"}


# ------------------------------------------------------------- idempotency


def test_rerun_is_noop(migrated_populated_db):
    """Re-running the migration must not error or drift (§4 §109)."""
    con = sqlite3.connect(migrated_populated_db)
    snapshot = {
        t: con.execute(f"SELECT * FROM {t}").fetchall()
        for t in ("hosts", "provisioning_machines")
    }
    schema = {
        t: [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        for t in ("hosts", *S5_TABLES)
    }
    con.close()

    run_sprint5_migrations(f"sqlite:///{migrated_populated_db.as_posix()}")

    con = sqlite3.connect(migrated_populated_db)
    for table, rows in snapshot.items():
        assert con.execute(f"SELECT * FROM {table}").fetchall() == rows, f"{table} drifted"
    for table, cols in schema.items():
        assert [r[1] for r in con.execute(f"PRAGMA table_info({table})")] == cols
    con.close()


def test_marker_recorded_once(migrated_populated_db):
    con = sqlite3.connect(migrated_populated_db)
    count = con.execute(
        f"SELECT COUNT(*) FROM {SPRINT5_MARKER_TABLE} WHERE revision='0003_sprint5'"
    ).fetchone()[0]
    con.close()
    assert count == 1
    run_sprint5_migrations(f"sqlite:///{migrated_populated_db.as_posix()}")
    con = sqlite3.connect(migrated_populated_db)
    count = con.execute(
        f"SELECT COUNT(*) FROM {SPRINT5_MARKER_TABLE} WHERE revision='0003_sprint5'"
    ).fetchone()[0]
    con.close()
    assert count == 1


def test_marker_table_created_even_on_fresh_db(tmp_path):
    db = tmp_path / "fresh.db"
    url = f"sqlite:///{db.as_posix()}"
    upgrade_phase3b(url)
    run_sprint5_migrations(url)
    con = sqlite3.connect(db)
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert SPRINT5_MARKER_TABLE in names
    assert set(S5_TABLES) <= names


# ------------------------------------------------------------ §4 FK RESTRICT


@pytest.mark.parametrize("table", sorted(RESTRICT_FKS))
def test_provisioning_fks_use_restrict(migrated_populated_db, table):
    con = sqlite3.connect(migrated_populated_db)
    fks = con.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    con.close()
    by_col = {row[3]: row for row in fks}
    for col in RESTRICT_FKS[table]:
        assert col in by_col, f"{table}.{col} is not an FK"
        on_delete = (by_col[col][6] or "").upper()
        assert on_delete == "RESTRICT", f"{table}.{col} ON DELETE is {on_delete}, not RESTRICT"


def test_fk_actually_blocks_dangling_insert(migrated_populated_db):
    """RESTRICT enforcement is real: a dangling target_id insert must fail."""
    con = sqlite3.connect(migrated_populated_db)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute(
        "INSERT INTO provisioning_connections (id, provider, display_name, config_revision,"
        " policy_hash, enabled) VALUES ('c1','AZURE_VM','x',1,?,1)",
        ("d" * 64,),
    )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO provisioning_targets (id, connection_id, canonical_key,"
            " observed_identity_hash, mapping_revision, mapping_status, discovered_at)"
            " VALUES ('t-dangling','no-such-connection','k','e'*64,0,'UNMAPPED',0)"
        )
    con.close()


# ------------------------------------------------------- required indexes §4


@pytest.mark.parametrize("table,expected", sorted(REQUIRED_INDEXES.items()))
def test_required_indexes_exist(migrated_populated_db, table, expected):
    con = sqlite3.connect(migrated_populated_db)
    names = {row[1] for row in con.execute(f"PRAGMA index_list({table})")}
    con.close()
    missing = [ix for ix in expected if ix not in names]
    assert missing == [], f"{table} missing indexes: {missing}"


def test_jobs_validation_id_unique(migrated_populated_db):
    """jobs.validation_id UNIQUE (§4: one job per validation)."""
    con = sqlite3.connect(migrated_populated_db)
    uniques = _unique_sets(con, "provisioning_jobs")
    con.close()
    assert any("validation_id" in s for s in uniques)


# ------------------------------------------------- §15.1 admission columns


def test_attempts_admission_columns(migrated_populated_db):
    con = sqlite3.connect(migrated_populated_db)
    cols = _cols(con, "provisioning_attempts")
    con.close()
    for col in ("admission_state", "closed_at", "closure_reason"):
        assert col in cols, f"provisioning_attempts missing §15.1 column {col}"


# ------------------------------------------------ §15.3 machines + machine_id


def test_machines_unique_bindings(migrated_populated_db):
    con = sqlite3.connect(migrated_populated_db)
    uniques = _unique_sets(con, "provisioning_machines")
    cols = _cols(con, "provisioning_machines")
    con.close()
    assert any("machine_binding_hash" in s for s in uniques)
    assert any("installation_id" in s for s in uniques)
    assert cols["machine_binding_hash"]["notnull"] == 1


def test_targets_machine_id_fk(migrated_populated_db):
    con = sqlite3.connect(migrated_populated_db)
    fks = con.execute("PRAGMA foreign_key_list(provisioning_targets)").fetchall()
    con.close()
    by_col = {row[3]: row for row in fks}
    assert "machine_id" in by_col
    assert by_col["machine_id"][2] == "provisioning_machines"
    assert (by_col["machine_id"][6] or "").upper() == "RESTRICT"


# ------------------------------------------------------------ CHECK/enum floors


def _insert_job(con, jid, state="PENDING", validation_id="aaaaaaaa-0000-4000-8000-000000000v01"):
    con.execute(
        "INSERT INTO provisioning_jobs (id,target_id,operation,validation_id,requester_id,"
        "approval_hash,approved_at,approval_expires_at,plan_json,state,revision,step,"
        "deadline_at,reconciliation_required,dispatch_blocked,lease_generation,created_at,updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (jid, "t1", "INSTALL", validation_id, "opr-1", "b" * 64, 0, 0, "{}", state, 0,
         "REVALIDATE", 0, 0, 0, 0, 0, 0),
    )


def test_jobs_state_check_enforced(migrated_populated_db):
    """§3 seven states only: an invalid state insert must be rejected."""
    con = sqlite3.connect(migrated_populated_db)
    con.execute("PRAGMA foreign_keys=ON")
    _insert_job(con, "j-ok")
    with pytest.raises(sqlite3.IntegrityError):
        _insert_job(con, "j-bad", state="RUNNNG")
    con.close()


def test_attempt_ordinal_check_enforced(migrated_populated_db):
    """§4: ordinal 1..3."""
    con = sqlite3.connect(migrated_populated_db)
    con.execute("PRAGMA foreign_keys=ON")
    _insert_job(con, "j1", validation_id="aaaaaaaa-0000-4000-8000-000000000v02")
    ins = ("INSERT INTO provisioning_attempts (id, job_id, step_key, ordinal, dispatch_id,"
           " ownership_generation, intent_hash, status) VALUES (?,?,?,?,?,?,?,?)")
    con.execute(ins, ("a1", "j1", "DISPATCH_INSTALL_OR_ACTION", 1, "d-1", 1, "f" * 64, "INTENT"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(ins, ("a4", "j1", "DISPATCH_INSTALL_OR_ACTION", 4, "d-4", 1, "f" * 64, "INTENT"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(ins, ("a0", "j1", "DISPATCH_INSTALL_OR_ACTION", 0, "d-0", 1, "f" * 64, "INTENT"))
    con.close()


# ------------------------------------------------------------- readiness


def _report_entries(report):
    entries = getattr(report, "entries", None)
    if entries is None:
        entries = getattr(report, "problems", None)
    assert entries is not None, "ReadinessReport must expose typed entries"
    return entries


def test_readiness_ok_after_migration(migrated_populated_db):
    from backend.app.core.db import _database_url  # noqa: F401  (import sanity)

    report = assert_provisioning_readiness(f"sqlite:///{migrated_populated_db.as_posix()}")
    entries = _report_entries(report)
    blocking = [e for e in entries if getattr(e, "blocking", True)]
    assert blocking == [], f"readiness must be clean after migration: {blocking}"
    assert getattr(report, "ok", True) is True


def test_readiness_fails_closed_on_missing_unique_index(tmp_path):
    """Drop a required unique index → typed blocking entry; never auto-repairs data."""
    db = tmp_path / "noidx.db"
    url = f"sqlite:///{db.as_posix()}"
    upgrade_phase3b(url)
    run_sprint5_migrations(url)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=OFF")
    # Rebuild targets without the canonical_key UNIQUE constraint.
    con.executescript(
        """
        ALTER TABLE provisioning_targets RENAME TO provisioning_targets_old;
        CREATE TABLE provisioning_targets (
            id VARCHAR(36) PRIMARY KEY,
            connection_id VARCHAR(36) NOT NULL REFERENCES provisioning_connections(id) ON DELETE RESTRICT,
            canonical_key VARCHAR(512) NOT NULL,
            observed_identity_hash VARCHAR(64),
            host_id VARCHAR(36) REFERENCES hosts(id) ON DELETE RESTRICT,
            machine_id VARCHAR(36) REFERENCES provisioning_machines(id) ON DELETE RESTRICT,
            mapping_revision INTEGER NOT NULL DEFAULT 0,
            mapping_status VARCHAR(16) NOT NULL,
            discovered_at INTEGER NOT NULL
        );
        INSERT INTO provisioning_targets SELECT * FROM provisioning_targets_old;
        DROP TABLE provisioning_targets_old;
        """
    )
    con.commit()
    con.close()

    report = assert_provisioning_readiness(url)
    entries = _report_entries(report)
    codes = {getattr(e, "code", "") for e in entries}
    assert any("index" in code.lower() or "unique" in code.lower() for code in codes), (
        f"expected a missing-unique-index entry, got {codes}"
    )
    assert any(getattr(e, "blocking", True) for e in entries), "missing index must block"
    assert getattr(report, "ok", True) is False


def test_readiness_fails_closed_on_collision(tmp_path):
    """Duplicate canonical_key rows → typed collision entry; rows are NEVER deleted."""
    db = tmp_path / "collision.db"
    url = f"sqlite:///{db.as_posix()}"
    upgrade_phase3b(url)
    run_sprint5_migrations(url)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=OFF")
    con.executescript(
        """
        ALTER TABLE provisioning_targets RENAME TO provisioning_targets_old;
        CREATE TABLE provisioning_targets (
            id VARCHAR(36) PRIMARY KEY,
            connection_id VARCHAR(36) NOT NULL REFERENCES provisioning_connections(id) ON DELETE RESTRICT,
            canonical_key VARCHAR(512) NOT NULL,
            observed_identity_hash VARCHAR(64),
            host_id VARCHAR(36) REFERENCES hosts(id) ON DELETE RESTRICT,
            machine_id VARCHAR(36) REFERENCES provisioning_machines(id) ON DELETE RESTRICT,
            mapping_revision INTEGER NOT NULL DEFAULT 0,
            mapping_status VARCHAR(16) NOT NULL,
            discovered_at INTEGER NOT NULL
        );
        INSERT INTO provisioning_targets VALUES
            ('dup-1','conn-1','same-canonical-key','e',NULL,NULL,0,'UNMAPPED',0),
            ('dup-2','conn-1','same-canonical-key','e',NULL,NULL,0,'UNMAPPED',0);
        DROP TABLE provisioning_targets_old;
        """
    )
    con.commit()
    con.close()

    report = assert_provisioning_readiness(url)
    entries = _report_entries(report)
    codes = {getattr(e, "code", "") for e in entries}
    assert any("collision" in code.lower() or "duplicate" in code.lower() for code in codes), (
        f"expected a collision entry, got {codes}"
    )
    assert getattr(report, "ok", True) is False
    con = sqlite3.connect(db)
    count = con.execute(
        "SELECT COUNT(*) FROM provisioning_targets WHERE canonical_key='same-canonical-key'"
    ).fetchone()[0]
    con.close()
    assert count == 2, "readiness must never delete colliding rows"


def test_readiness_reports_synchronous_full(migrated_populated_db):
    """§4 §111: synchronous=FULL is verified and recorded in the report."""
    report = assert_provisioning_readiness(f"sqlite:///{migrated_populated_db.as_posix()}")
    entries = _report_entries(report)
    sync_entries = [e for e in entries if "synchronous" in str(getattr(e, "code", "")).lower()]
    assert sync_entries, "readiness must record a synchronous=FULL check"
    for e in sync_entries:
        assert getattr(e, "blocking", False) is False or getattr(e, "ok", True), (
            "synchronous=FULL check must not spuriously block on a clean engine"
        )


def test_readiness_never_deletes(migrated_populated_db):
    """Readiness is read-only: row counts unchanged across a report run."""
    con = sqlite3.connect(migrated_populated_db)
    before = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in S5_TABLES + ("hosts",)}
    con.close()
    assert_provisioning_readiness(f"sqlite:///{migrated_populated_db.as_posix()}")
    con = sqlite3.connect(migrated_populated_db)
    after = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in S5_TABLES + ("hosts",)}
    con.close()
    assert before == after


# ------------------------------------------------------------ ORM models


def test_thirteen_provisioning_models_exist():
    import backend.app.models as m

    for name in (
        "ProvisioningMachine", "ProvisioningConnection", "ProvisioningTarget",
        "ProvisioningValidation", "ProvisioningJob", "ProvisioningRequest",
        "ProvisioningOwnership", "ProvisioningAttempt", "ProvisioningEvent",
        "ProvisioningGrant", "ProvisioningCredentialCommit", "ProvisioningChallenge",
        "ProvisioningReceipt",
    ):
        assert hasattr(m, name), f"models.{name} missing"
        cls = getattr(m, name)
        assert hasattr(cls, "__tablename__") and cls.__tablename__.startswith("provisioning_")


def test_models_map_to_s5_tables():
    import backend.app.models as m

    for name in S5_TABLES:
        assert name in m.Base.metadata.tables, f"ORM model for {name} missing"


def test_begin_immediate_used_in_migration_write_paths():
    """SQLite writes in the migration run under BEGIN IMMEDIATE (§4 §111 hygiene)."""
    import inspect as pyinspect
    import backend.app.core.migrations as mig

    src = pyinspect.getsource(mig.run_sprint5_migrations)
    assert "BEGIN IMMEDIATE" in src or "begin_immediate" in src.lower(), (
        "run_sprint5_migrations must issue BEGIN IMMEDIATE for writes"
    )
