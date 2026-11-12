# Phase 3B Acceptance → Phase 6 Release Readiness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Phase 3B formal acceptance, close the Phase 4 (multi-host control plane) and Phase 5 (orchestration completeness) gaps against PRD-v2.0/ROADMAP, and harden NimbusOps to a v1 release candidate.

**Architecture:** FastAPI + SQLAlchemy + SQLite backend; React/Vite frontend; Python agent on enrolled hosts. All changes additive; existing contracts preserved (mission §6: avoid rewrites; agent protocol compat is a stop condition).

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2, pytest; TypeScript, React 19, Vite, Vitest.

**Spec:** docs/PRD-v2.0.md (FR-03/09/19, AC-15/17), docs/ROADMAP.md, docs/PHASE3B_*.md, mission brief §2–§5.

## Global Constraints

- Baseline main `9902667`; never rewrite history; feature branch only.
- Agent protocol: heartbeat/telemetry/poll/result payloads must remain backward-compatible (additive fields only).
- No production mutation; DavidLab read-only; no push/merge.
- All destructive/credential tests use isolated fixtures (per-test SQLite).
- `sim-` hostnames rejected server-side (existing defense — keep).
- Tests: pytest.ini covers backend/tests, agent/tests, backend/tests_integration.

## Review Focus

- Pagination defaults must not break existing `HostListResponse` consumers (agent, frontend, tests) — additive `page/page_size/total` fields, count unchanged.
- Operation history endpoint must not leak other-host results (IDOR probe).
- Inventory snapshot must respect stale data honesty (FR-03: `observed_at`, age visible; never present stale as fresh).
- Rate limiter must not lock out legit operators in tests (bounded, configurable, test-mode off or tiny).
- WAL pragma must be applied on the actual engine used by the app (verified via `PRAGMA journal_mode` readback in test).

---

## Phase 3B — Final Acceptance (gaps only)

### Task 1: Malformed-credential + concurrency coverage

**Files:**
- Test: `backend/tests/test_phase3b_acceptance_gaps.py` (create)

**Interfaces:**
- Consumes: existing fixtures (`client`, `enrolled_host`, `enroll_token`), `POST /api/v1/operators/login`, `POST /api/v1/bootstrap-tokens`, `POST /api/v1/agents/enroll`.
- Produces: PASS evidence lines recorded in `docs/PHASE3B_FINAL_ACCEPTANCE.md`.

- [ ] **Step 1: Write failing tests** — malformed Authorization headers (no Bearer, empty token, non-UTF8 bytes, oversized token), malformed login JSON (missing fields, wrong types), 32-parallel bootstrap redemption → exactly 1 success + 31 conflicts (mirrors AC-11 pattern).
- [ ] **Step 2: Run — expect RED where behavior is missing** (e.g., 500 instead of 401/422 on malformed input).
- [ ] **Step 3: Fix any 5xx/misclassified responses found; rerun GREEN.**
- [ ] **Step 4: Full suite green; commit `test: phase 3B acceptance gap coverage (malformed creds, token concurrency)`.**

### Task 2: PHASE3B_FINAL_ACCEPTANCE.md

**Files:**
- Create: `docs/PHASE3B_FINAL_ACCEPTANCE.md`

- [ ] Consolidate: O1–O8 mapping, test gates (153→new), live connectivity evidence (375/375, 185 s window, reconnect PASS — reused per mission §2), migration/rollback evidence, threat-model closure status, residual minors. Commit `docs: phase 3B final acceptance`.

## Phase 4 — Multi-host management gaps

### Task 3: Host list pagination + filtering

**Files:**
- Modify: `backend/app/services/hosts.py` (`list_hosts` → paginated variant with filter)
- Modify: `backend/app/api/public.py` (`GET /hosts` query params)
- Modify: `backend/app/schemas/__init__.py` (additive PageMeta)
- Test: `backend/tests/test_host_pagination.py` (create)

- [ ] RED: create 25 hosts; `?page=2&page_size=10` → 10 items, meta `{page:2,total_pages:3,total:25}`; `?status=online` filters; `?hostname=sub` filters; no params → legacy shape preserved (back-compat test pins `count`).
- [ ] GREEN: implement `list_hosts_paginated(db, page, page_size, status, hostname_q)`.
- [ ] Full suite; commit `feat: host list pagination and filtering (FR-09)`.

### Task 4: Host capabilities + environment metadata (FR-19)

**Files:**
- Modify: `backend/app/models/__init__.py` (Host: `environment` col, additive)
- Modify: `backend/app/core/migrations.py` (additive column + backfill `PRIVATE`)
- Modify: `backend/app/api/agents.py` (heartbeat accepts optional `environment`)
- Modify: `backend/app/schemas/__init__.py` (HostOut additive fields)
- Test: `backend/tests/test_host_environment.py` (create)

- [ ] RED: enroll with `environment:"PUBLIC-CLOUD"` → HostOut carries it; default enroll → `PRIVATE`; unknown environment → 422.
- [ ] GREEN via additive migration column.
- [ ] Suite; commit `feat: host environment metadata (FR-19)`.

### Task 5: Frontend — real-API fleet dashboard states

**Files:**
- Modify: `frontend/src/views/Servers.tsx`, `frontend/src/components/ServerList.tsx`, `frontend/src/api/client.ts`, `frontend/src/api/types.ts`
- Test: `frontend/src/views/__tests__/servers.test.tsx` (extend)

- [ ] RED: loading skeleton, error retry button, empty state, environment filter chips (additive UI; existing tests stay green).
- [ ] GREEN; `npm test`, `npm run build`; commit `feat: fleet dashboard real-API states and environment filter`.

## Phase 5 — Orchestration completeness

### Task 6: Docker inventory endpoint (FR-03) + RESTART op + injection pins

**Files:**
- Modify: `agent/nimbusops_agent/docker_exec.py` (add `inventory` op — allowlisted, read-only `docker ps --format`; add `restart` to allowlist)
- Modify: `agent/nimbusops_agent/worker.py` (route inventory + restart)
- Modify: `backend/app/api/agents.py` (accept inventory snapshots on heartbeat or dedicated endpoint)
- Modify: `backend/app/models/__init__.py` + `backend/app/core/migrations.py` (`inventory_snapshots` table)
- Modify: `backend/app/api/public.py` (`GET /hosts/{id}/inventory`, requires nothing new — reads stay public per threat model)
- Modify: `backend/app/services/deployments.py` + `backend/app/api/applications.py` (RESTART op_type end-to-end)
- Test: `agent/tests/test_inventory.py`, `agent/tests/test_injection_pins.py`, `backend/tests/test_inventory_api.py`, `backend/tests/test_restart_op.py` (create)

- [ ] RED (agent): inventory returns parsed containers w/ id,names,image,state,labels,observed_at; docker missing → explicit `(ok=False, detail)` no raise.
- [ ] RED (agent pins): container-name args with `;`, spaces, `$()`, `--privileged`, backticks never reach argv (fixed-argv proof).
- [ ] RED (backend): heartbeat with `inventory` payload persists snapshot; GET returns latest with `age_seconds`; no snapshot → 404 structured error; stale never labeled fresh.
- [ ] RED (restart): POST restart → 202 op RESTART; agent result honored; docker-disabled host → 403.
- [ ] GREEN; suite; commit `feat: docker inventory, restart op, injection pins (FR-03/05)`.

### Task 7: Operation history API

**Files:**
- Modify: `backend/app/api/applications.py` (`GET /operations?host_id=&status=&limit=`, `GET /operations/{id}/events`)
- Modify: `backend/app/schemas/__init__.py`
- Test: `backend/tests/test_operation_history.py` (create)

- [ ] RED: filter by host/status/pagination; events append-only ordering; **IDOR probe: operation of host A returns full detail to unauthenticated read (allowed by threat model) but events never contain token material** (pin sanitization).
- [ ] GREEN; suite; commit `feat: operation history and event query API (FR-08)`.

### Task 8: Frontend — operations history UI

**Files:**
- Modify: `frontend/src/views/Activity.tsx` (server-backed history list w/ filters), `frontend/src/api/client.ts`, `types.ts`
- Test: `frontend/src/views/__tests__/activity.test.tsx` (create)

- [ ] RED: renders operations from API; status filter; loading/empty/error states; risky-action confirm dialog exists on deploy/stop (reuse existing modal pattern).
- [ ] GREEN; build; commit `feat: activity view real operation history (FR-08 UI)`.

## Phase 6 — Hardening & release readiness

### Task 9: Login rate limiting

**Files:**
- Modify: `backend/app/core/config.py` (`login_rate_limit_attempts`, `login_rate_limit_window_seconds`)
- Modify: `backend/app/api/operators.py` (in-memory sliding window per username+IP)
- Test: `backend/tests/test_login_rate_limit.py` (create)

- [ ] RED: 6th failed login within window → 429 `RATE_LIMITED`; success resets; window expiry restores; test override sets tiny window.
- [ ] GREEN; suite; commit `feat: login rate limiting (threat model limitation 6)`.

### Task 10: Security headers + endpoint auth review

**Files:**
- Modify: `backend/app/main.py` (middleware: X-Content-Type-Options, X-Frame-Options DENY, Referrer-Policy, CSP for /api/docs)
- Test: `backend/tests/test_security_headers.py` (create)

- [ ] RED: headers present on /api/v1/health and /api/docs.
- [ ] GREEN; commit `feat: security headers`.

### Task 11: SQLite WAL + graceful shutdown + structured logging

**Files:**
- Modify: `backend/app/core/db.py` (WAL pragma on connect, idempotent)
- Modify: `backend/app/main.py` (shutdown handler logs clean stop; request logging w/o query strings)
- Test: `backend/tests/test_wal_mode.py` (create)

- [ ] RED: `PRAGMA journal_mode` on a session connection returns `wal`.
- [ ] GREEN; suite; commit `feat: WAL mode + shutdown logging hygiene`.

### Task 12: Dependency + secrets review (audit, no code change unless finding)

- [ ] `pip list --outdated`, `npm audit` (record only; upgrades only for Critical/Important with tests).
- [ ] Grep repo for logged secrets patterns; verify `.env` in .gitignore; record in security review doc. Commit `docs: dependency and secrets audit (phase 6)` if findings require fixes; else evidence recorded in doc.

### Task 13: Release documentation suite

**Files:**
- Create: `docs/PHASE6_SECURITY_REVIEW.md`, `docs/PHASE6_RELEASE_READINESS.md`, `docs/NIMBUSOPS_V1_RELEASE_CANDIDATE.md`, `docs/RELEASE_RUNBOOK.md`, `docs/ENV_REFERENCE.md`, `docs/BACKUP_RESTORE.md`, `docs/OPERATOR_PROVISIONING.md`, `docs/TROUBLESHOOTING.md`

- [ ] Write from implemented reality (no aspiration); known limitations explicit; runbook references exact commands verified this session. Commit `docs: v1 release candidate documentation suite`.

### Task 14: Final verification + scorecard

- [ ] Full backend suite, frontend suite, `tsc -b && vite build`.
- [ ] Agent-contract compatibility check: heartbeat/telemetry/poll/result schema diff vs agent client (test).
- [ ] Produce final scorecard in the engineering report (chat), update worktree HEAD evidence.

## Risk classification

- Low: Tasks 1,2,7,9,10,11,13,14 (isolated or additive).
- Medium: Tasks 3,4,6,8,12 (schema additive col/table; agent code touch — protocol additive only; frontend flows).
- Rollback: revert branch commits; DB additive columns/tables ignored by old code (verified pattern from 3B).
