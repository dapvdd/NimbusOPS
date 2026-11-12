# NimbusOps Backup, Restore, and Migration Guide

Scope: the control server's SQLite database (hosts, credentials hashes,
telemetry, operations, audit). Agent identity files are backed up per host.

## 1. Backup (safe, online)

SQLite is live while the server runs. Use the online backup API — **never copy
the file while WAL is active without the backup API or `wal_checkpoint`**:

```python
import sqlite3
src = sqlite3.connect("backend/nimbusops.db")
dst = sqlite3.connect("backup/nimbusops-snapshot.db")
src.backup(dst)            # consistent snapshot, safe while serving
dst.close(); src.close()
```

Verified in this program: staging snapshot produced a consistent clone while
the source served traffic; the source DB SHA-256 was unchanged by the process.

Also back up:
- `.env` (contains the pepper + enrollment token — store separately from DB backups).
- Each agent's `~/.nimbusops/agent.json` if you want hosts to survive control-plane
  loss without re-enrollment (contains the agent token).

## 2. Restore

1. Stop the control server.
2. Replace the database file with the snapshot.
3. Start the server: `upgrade_phase3b()` runs at boot and converges the schema
   (additive, idempotent — safe to run against any Phase 2/3B-era snapshot).

## 3. Rollback of application upgrades

- All schema changes in Phases 3B–6 are **additive** (new tables/columns with
  defaults; `inventory_snapshots` is derived data and can be dropped freely).
- To roll back the app: stop, check out the previous tag/commit, start. Old code
  ignores new columns/tables; no downgrade script is required.
- Data written by new code (inventory snapshots, RESTART ops) is simply unused
  by the older version.

## 4. Retention

- Telemetry: bounded at `NIMBUSOPS_TELEMETRY_RETENTION_ROWS` per host (pruned
  inline on ingest; verified by tests).
- Operations/audit: unbounded by design (small rows; append-only audit is a
  feature). Schedule an operational backup cadence accordingly.

## 5. Integrity checks

```sql
PRAGMA integrity_check;    -- after restore, before serving
PRAGMA journal_mode;       -- expect "wal"
```
