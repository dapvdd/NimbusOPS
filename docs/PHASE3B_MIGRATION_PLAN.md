# Phase 3B Migration Plan — DB Schema, Backward Compatibility, Rollback

**Status:** DESIGN — NOT IMPLEMENTED.
**Date:** 2026-11-10 · Branch: `feat/phase3b-secure-enrollment`
**Baseline:** SQLite via `Base.metadata.create_all()` (`core/db.py:43-46`); **no Alembic** exists today.

---

## 1. Current Schema (Phase 1–2, verified)

Tables: `hosts`, `telemetry`, `enrollment_audit`, `deployment_templates`, `managed_deployments`, `deployment_operations`, `operation_events`.

Relevant existing columns on `hosts`: `id (uuid pk)`, `hostname (unique)`, `agent_token_hash`, `enrolled_at`, `revoked_at`, `agent_version`, `platform`, `platform_release`, `cpu_cores`, `total_memory_bytes`, `boot_time`, `last_seen_at`, `last_telemetry_at`, `is_revoked`.

No `enrollment_status`, no `docker_enabled`, no bootstrap-token table, no operator tables.

**Live data (inspected read-only):** `david-lab` (id `5ca406e8…`, enrolled 2026-11-09, active, `is_revoked=0`, has telemetry + 1 managed deployment + 9 operations) and `local-probe` (inactive). This is the "existing DavidLab host" that must survive migration untouched.

---

## 2. Phase 3B Schema Changes

### 2.1 New table: `bootstrap_tokens`

```sql
CREATE TABLE bootstrap_tokens (
    id            VARCHAR(36)  PRIMARY KEY,          -- uuid4
    token_hash    VARCHAR(64)  NOT NULL UNIQUE,      -- keyed SHA-256, same scheme as agent tokens
    hostname      VARCHAR(255) NOT NULL,             -- scope: hostname this token may enroll
    created_by    VARCHAR(36)  NOT NULL,             -- operator id (FK operators.id, nullable during transition)
    created_at    DATETIME     NOT NULL,
    expires_at    DATETIME     NOT NULL,
    consumed_at   DATETIME     NULL,
    consumed_by   VARCHAR(36)  NULL,                 -- host id that consumed it (FK hosts.id)
    revoked_at    DATETIME     NULL
);
CREATE INDEX ix_bootstrap_tokens_hostname ON bootstrap_tokens (hostname);
```

Single-use enforcement: consumption is an atomic `UPDATE ... SET consumed_at=?, consumed_by=? WHERE id=? AND consumed_at IS NULL AND revoked_at IS NULL AND expires_at > now`; `rowcount==0` → token expired/used/revoked.

### 2.2 New table: `operators`

```sql
CREATE TABLE operators (
    id            VARCHAR(36)  PRIMARY KEY,
    username      VARCHAR(64)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,             -- PBKDF2/scrypt via passlib-style KDF (NOT the fast token hash)
    role          VARCHAR(16)  NOT NULL,             -- ADMIN | VIEWER
    created_at    DATETIME     NOT NULL
);
```

### 2.3 New table: `operator_sessions`

```sql
CREATE TABLE operator_sessions (
    id          VARCHAR(36) PRIMARY KEY,
    operator_id VARCHAR(36) NOT NULL REFERENCES operators(id),
    token_hash  VARCHAR(64) NOT NULL UNIQUE,
    created_at  DATETIME    NOT NULL,
    expires_at  DATETIME    NOT NULL,
    revoked_at  DATETIME    NULL
);
```

### 2.4 New table: `host_events` (append-only audit)

```sql
CREATE TABLE host_events (
    id       INTEGER      PRIMARY KEY AUTOINCREMENT,
    at       DATETIME     NOT NULL,
    host_id  VARCHAR(36)  NULL,                     -- null for pre-enrollment events
    event    VARCHAR(32)  NOT NULL,                 -- e.g. BOOTSTRAP_ISSUED, ENROLLED, CREDENTIAL_ROTATED, REVOKED, DOCKER_ENABLED, DOCKER_DISABLED
    actor    VARCHAR(64)  NOT NULL,                 -- operator username or "agent"
    detail   VARCHAR(512) NULL                      -- sanitized, no secret material
);
CREATE INDEX ix_host_events_host ON host_events (host_id, at);
```

### 2.5 New columns on `hosts` (nullable first, then backfill)

| Column | Type | Default (new rows) | Backfill (existing rows) |
|---|---|---|---|
| `enrollment_status` | VARCHAR(16) NOT NULL | `'PENDING'` at insert (agent sets via enroll) | `'ENROLLED'` for all pre-3B hosts |
| `docker_enabled` | INTEGER/Boolean NOT NULL | `0` (false) | `0` (false) for all hosts |
| `credential_version` | INTEGER NOT NULL | `1` | `1` |

Backfill sets `david-lab` and `local-probe` to `ENROLLED` — they were enrolled under the old flow and are therefore considered enrolled. `docker_enabled=0` means Docker ops are **disabled by default on all hosts, including the existing DavidLab host**, until separately authorized (mission requirement 16).

### 2.6 New columns on `deployment_operations` (claim-timeout support, PRD FR-15)

| Column | Type | Notes |
|---|---|---|
| (exists) `claimed_at` | DATETIME NULL | Already present in Phase 2 |
| `timeout_at` | DATETIME NULL | Set at claim time (`claimed_at + claim_timeout`); used by the reconciler |

No table renames. No column deletions. No type changes on existing columns.

---

## 3. Migration Mechanism

### 3.1 Recommended: introduce Alembic

The repo has no migration tool. Phase 3B introduces **Alembic** with SQLAlchemy (`backend/alembic/`), because multi-host lifecycle changes are the first schema evolution that cannot be solved by `create_all()` on new tables alone (existing `hosts` rows need backfill).

- `alembic init backend/alembic` (script location `backend/alembic`, target metadata `backend.app.models.Base.metadata`).
- Initial revision: autogenerate baseline against the Phase 1–2 schema (no-op stamp for existing DBs).
- Revision `0002_phase3b`: the changes in §2.

### 3.2 Fallback if Alembic is rejected (open decision O-DB-1)

A hand-written, idempotent `upgrade_phase3b(db)` function run at startup (after `create_all()`):
- `create_all()` creates the four new tables (Alembic-free path).
- Check `PRAGMA table_info(hosts)`; add missing columns via `ALTER TABLE hosts ADD COLUMN ...` (SQLite supports ADD COLUMN with constant defaults).
- Backfill `enrollment_status`/`docker_enabled` for rows where NULL (one UPDATE).
- Guarded by a version marker row so it runs once.

This is simpler but leaves no migration history. Alembic is recommended for Phase 3B and becomes mandatory anyway before any PostgreSQL move (PRD §5).

### 3.3 SQLite → PostgreSQL (deferred)

PRD defers PostgreSQL until measured concurrency needs justify it. Phase 3B must not block on it. Alembic introduced in §3.1 makes a later PostgreSQL move a config change plus `alembic upgrade head`. No Phase 3B code may rely on SQLite-specific behavior beyond what `core/db.py` already isolates (pragmas).

---

## 4. Backward Compatibility (existing hosts)

| Concern | Guarantee | How |
|---|---|---|
| DavidLab identity | `host_id` unchanged; telemetry, deployments, operations retained | Migration only adds columns/backfills; no row deletion |
| DavidLab credential | Existing agent token keeps working after upgrade | `agent_token_hash`, pepper scheme untouched; agent needs no re-enroll |
| DavidLab Docker ops | Blocked after upgrade until explicitly enabled | `docker_enabled=0` backfilled; `deploy` service returns 403 until operator enables (mission req. 16) — this is a deliberate, documented behavior change |
| Old enrollment flow | `enrollment_token` env still valid during transition window | Phase 3B accepts both `enrollment_token` (legacy, maps to single-use internal bootstrap consumption) and `bootstrap_token`; legacy path is deprecated in the same release that adds bootstrap tokens and removed no earlier than Phase 4 (open decision O-5) |
| Old heartbeat response | `docker_enabled` added to `HeartbeatResponse` | Additive field; Phase 2 agent code ignores unknown JSON fields (httpx JSON passthrough) — verified pattern in `client.py:101-119` (payload dicts tolerate extra keys) |
| Agent version skew | Old agent + new backend works | Old agent never calls new endpoints; heartbeat/telemetry/poll contracts unchanged |
| Frontend version skew | New backend + old frontend works | `HostOut` gains additive fields; React types in `frontend/src/api/types.ts` are structural — additive JSON fields are ignored by TS at runtime |
| `is_revoked` flag | Still meaningful | Kept in sync: revoke endpoint sets both `is_revoked=1` and `enrollment_status='REVOKED'` |

---

## 5. Recovery After Control-Plane Restart

- All state is in SQLite (no in-memory auth state). Restart recovery is: `create_all()` (idempotent) + migration guard (idempotent) + seed templates (idempotent) — the existing startup sequence in `main.py:25-33`, extended with the migration step.
- Operator sessions survive restart (persisted in `operator_sessions` with `expires_at`); expired sessions are rejected and lazily purged.
- Pending bootstrap tokens survive restart; the TTL check uses wall-clock `expires_at`.
- In-flight `RUNNING` operations survive restart; the claim-timeout reconciler (new, background task or on-poll check) re-queues ops whose `timeout_at` has passed — this also closes the pre-existing stuck-RUNNING gap (threat model I4) without a dedicated scheduler.

---

## 6. Rollback Strategy

| Artifact | Rollback procedure | Data impact |
|---|---|---|
| Phase 3B app code | `git checkout main` (or revert the merge); redeploy previous build | None — old code ignores new columns/tables |
| New columns (`enrollment_status`, `docker_enabled`, `credential_version`) | No-op for old code; retained harmlessly | None. **No column drop is performed** (SQLite DROP COLUMN is destructive and unnecessary — old code ignores extras) |
| New tables (`bootstrap_tokens`, `operators`, `operator_sessions`, `host_events`) | Retained harmlessly; old code never reads them | None |
| Alembic revision | `alembic downgrade 0001_baseline` (drops only Phase 3B structures) or leave tables in place | Hosts/telemetry untouched either way |
| Existing agent | Old agent binary keeps working against rolled-back backend | None |
| DavidLab host | Never deleted or modified by any rollback | Preserved by construction (additive-only migration) |

**Rollback safety rule:** Phase 3B migrations are **additive-only** (new tables, new nullable-then-backfilled columns, no renames, no deletes, no type changes). This makes every rollback a pure code revert; the schema never needs reversing, and the DavidLab host cannot be damaged by rolling back.

---

## 7. Migration Test Gates (deterministic)

1. **Fresh DB**: `create_all()` + migration on empty DB → all tables/columns exist; template seed runs; `/health` OK.
2. **Legacy DB upgrade**: seed a Phase 1–2-shaped DB (hosts with no new columns, david-lab-like row), run migration → columns backfilled `ENROLLED`/`false`; row count, host ids, telemetry counts unchanged; agent token of a pre-3B host still authenticates (heartbeat 200).
3. **Re-run idempotency**: run migration twice → no duplicate backfills, no errors, no schema drift.
4. **Rollback simulation**: run migration, roll code back to `main` behavior (old code path) → old code functions against migrated DB (additive columns ignored).
5. **DavidLab simulation**: replica row with telemetry + managed deployment + operations survives migration byte-for-byte except the three new column values.
