# NimbusOps Phase 6 — Release Readiness

Date: 2026-11-12 · Branch: `feat/autonomous-phase4-6` · Verdict: **RELEASE CANDIDATE (v1.0.0-rc1)**

## 1. Quality gates (executed this program)

| Gate | Command | Result |
| --- | --- | --- |
| Backend + agent regression | `python -m pytest -q` | **208 passed**, 0 failed |
| Frontend regression | `npm test` | **48 passed**, 0 failed |
| TypeScript + production build | `npm run build` | green (tsc -b + vite build) |
| CI parity | .github/workflows/ci.yml jobs (pytest, frontend build, agent tests) | suite content matches CI's three jobs locally |

## 2. Feature completeness against mission phases

**Phase 4 (multi-host)** — PASS (within defined scope)
- Persistent registry, enrollment lifecycle + state machine, heartbeats/health,
  metadata (capabilities: cpu/mem/platform/boot), environment grouping (FR-19),
  revocation + credential rotation with grace, audit events, pagination +
  hostname filtering (FR-09), server-side RBAC, sim-host isolation.
- Frontend: real-API fleet dashboard with environment chips/filter, loading/
  error/empty/recovery states, host detail, enrollment workflow (bootstrap UX).

**Phase 5 (orchestration)** — PASS (within defined scope)
- Docker inventory (FR-03): agent read-only snapshot → heartbeat ingest →
  `GET /hosts/{id}/inventory` with observed_at/age_seconds (stale honesty).
- Container lifecycle: DEPLOY/START/STOP + **RESTART** (new), all allowlisted,
  ADMIN-only, docker_enabled-gated both server-side and agent-side.
- Durable op queue: atomic claim, claim-timeout reconciler, idempotent dedup,
  append-only per-op events, operation history API (FR-08) with filters.
- UI: real operation history + status filter + failure detail + retry.
- No shell anywhere in the agent's Docker path (fixed argv, pinned by tests).

**Phase 6 (hardening)** — PASS (within defined scope)
- Rate limiting, security headers, Bearer strictness, WAL, dependency/secrets
  review, threat-model closure; documentation suite (runbook, env reference,
  backup/restore, provisioning, troubleshooting, security review, known
  limitations, release candidate summary).

## 3. Readiness checklist

- [x] All mutations authenticated + authorized (RBAC server-side)
- [x] Login rate limiting active
- [x] Security headers on every response
- [x] Tokens hashed at rest; bootstrap tokens single-use + atomic
- [x] No secrets in repo; .env ignored; logs sanitized (pinned)
- [x] SQLite WAL + busy_timeout; additive-idempotent startup migrations
- [x] Operation queue: claim timeouts, dedup, reconnect-safe delivery
- [x] Health endpoint + reconciler + structured logs without secret material
- [x] Full regression suites green; build green
- [x] Agent protocol backward-compatible (heartbeat additions are optional
      fields; legacy server responses unchanged — verified by contract tests)
- [x] Documentation suite present and grounded in verified commands
- [ ] Live multi-host validation on real remote hosts — **BLOCKED (external)**:
      requires host VMs + network authorization not granted in this program.
      Local staging validation (Phase 3B evidence) covers the single-host path.
- [ ] TLS termination — deployment-environment concern (runbook notes proxy).

## 4. Known limitations (also in NIMBUSOPS_V1_RELEASE_CANDIDATE.md)

1. Reads are public per the trusted-local threat model — deploy behind a
   boundary; operator-authenticated reads deferred.
2. Rate limiter is in-memory per process — run a single uvicorn worker.
3. Legacy shared-token enrollment path still exists (leave token unset in prod).
4. No Alembic — the hand-written additive migrator is the live path (O7 deviation).
5. Dev-chain npm advisories — upgrade majors in maintenance window.
6. Compose/backup-restore (Restic) from PRD M4 are out of v1 scope.

## 5. Deployment recommendation

Single control-plane process on a trusted network segment, loopback- or
proxy-bound, SQLite with WAL, one agent per managed host. Follow
`docs/RELEASE_RUNBOOK.md`; verify with its §7 checklist before exposing
anything beyond loopback.
