# NimbusOps v1.0.0 Release Candidate

Date: 2026-11-12 · Branch: `feat/autonomous-phase4-6` · Baseline: main `9902667`

## What NimbusOps v1 is

A hybrid-infrastructure control plane: a FastAPI + SQLite server holding the
host registry, credentials, telemetry, and a durable Docker operation queue; a
React SPA for fleet visibility and operations; and a Python agent per managed
host that heartbeats, reports telemetry + read-only Docker inventory, and
executes a strict allowlist of container operations.

## Release scope (implemented + tested in this program)

| Area | Delivered |
| --- | --- |
| Multi-host registry | Enrollment (bootstrap single-use + legacy), lifecycle state machine, revocation, rotation w/ grace, environment metadata, pagination/filtering, audit events |
| Fleet UI | Real-API dashboard, environment chips + filter, host detail, enrollment workflow, loading/error/empty/recovery states |
| Orchestration | DEPLOY/START/STOP/RESTART (allowlisted), docker_enabled gates (server+agent), durable queue w/ atomic claim + timeout reconciler + dedup, inventory snapshots, operation history + events API, history UI |
| Security | Operator RBAC (ADMIN/VIEWER), session bearer (strict Bearer scheme), login rate limiting, security headers, hashed tokens, no-secret logs, injection-proof agent argv |
| Reliability | WAL, busy_timeout, bounded telemetry retention, claim timeouts, natural reconnect, additive idempotent migrations |
| Docs | Runbook, env reference, backup/restore, provisioning, troubleshooting, threat-model-based security review, readiness checklist |

## Verification summary

- Backend + agent: **208 passed** (baseline 153 → +55 new tests this program).
- Frontend: **48 passed** (baseline 42 → +6, incl. migrated legacy Activity test).
- Production build: green. CI-equivalent checks executed locally.
- Phase 3B live evidence (single real host, 375/375 requests, 185 s window,
  natural reconnect, zero mutations) remains valid; no code change invalidated it.

## Explicit out-of-scope / known limitations

1. Public reads (trusted-local threat model). Put a network boundary in front.
2. In-memory login rate limiter (single-process deployment assumption).
3. Legacy shared-token enrollment remains available for transition.
4. No Alembic; the additive hand-written migrator is authoritative.
5. Dev-chain (vitest/vite/react-router) advisories — none reachable in
   production assets; schedule major upgrades.
6. PRD M4 items (Restic backup/restore, Compose, multi-deploy orchestration)
   are future work.
7. Multi-host live validation on real remote hosts was BLOCKED in this program
   (no host authorization); isolation is covered by the concurrent/hostname
   test matrix locally.

## Release verdict

**GO as v1.0.0-rc1** for controlled (non-public) deployment, per
`docs/PHASE6_SECURITY_REVIEW.md` §9 and `docs/PHASE6_RELEASE_READINESS.md` §5.
Recommended next actions: (1) merge after human review of this branch, (2) tag
v1.0.0-rc1, (3) schedule dev-dependency majors + operator-authenticated reads
for v1.1, (4) arrange a live two-host validation window (separate authorization).
