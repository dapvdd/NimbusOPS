# Phase 3B Secure Enrollment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement secure real-host enrollment: operator auth, single-use bootstrap tokens, per-host credential lifecycle (rotate/revoke), host lifecycle state machine, Docker default-off per host — without breaking Phase 1 monitoring, Phase 2 Docker ops, or Phase 3A simulation isolation.

**Architecture:** Extend the existing FastAPI/SQLite control plane additively (new tables, new columns, no renames/deletes). Bootstrap tokens decouple enrollment from infrastructure access; operator sessions gate mutations; the existing agent bearer-token model is preserved for telemetry/commands.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite (+Alembic), passlib-style KDF for operator passwords, pytest, Vitest/RTL.

**Spec:** `docs/PHASE3B_ARCHITECTURE.md`, `docs/PHASE3B_THREAT_MODEL.md`, `docs/PHASE3B_API_CONTRACT.md`, `docs/PHASE3B_MIGRATION_PLAN.md`

## Global Constraints

- Additive-only migrations; DavidLab host (`5ca406e8…` in local DB) must never be mutated/deleted.
- No dependency on Tailscale for application-layer auth; TLS remains deployment responsibility.
- Simulated `sim-` identifiers rejected server-side before any data access.
- Existing agent token hash scheme (keyed SHA-256, `core/security.py`) unchanged.
- Public read endpoints stay unauthenticated (trusted-local model, Phase 3B scope).
- No `docker system prune`, no production mutations, no deployments during implementation.
- Do not weaken existing security checks; `test_unauthed_mutation_rejected` (test_deployments.py:312-318) is REWRITTEN to assert 401 once operator auth lands.

## Review Focus

- **Expired bootstrap token** → agent gets `410 BOOTSTRAP_TOKEN_EXPIRED`, not a silent success. (Pinned: Task 3 test)
- **Replayed bootstrap token** → second enrollment with same token → `409 BOOTSTRAP_TOKEN_CONSUMED`. (Pinned: Task 3)
- **Revoked host re-enrollment without operator bootstrap** → 401, never silently restores credential. (Pinned: Task 5)
- **Docker op on `docker_enabled=false` host** → 403 `DOCKER_NOT_AUTHORIZED`; op never queued. (Pinned: Task 6)
- **Control-plane restart mid-enrollment** → bootstrap token and session state survive; re-run idempotent. (Pinned: Task 4 restart test)

---

## Milestones (each = independently shippable, tests green, rollback = code revert)

### Task 1: Alembic baseline + migration 0002 (schema only)

**Files:**
- Create: `backend/alembic/` (env.py, versions/0001_baseline.py, 0002_phase3b.py), `backend/alembic.ini`
- Modify: `backend/app/models/__init__.py` (new models), `backend/app/main.py:25-33` (lifespan runs migration)
- Test: `backend/tests/test_migration.py`

**Interfaces:**
- Produces: `bootstrap_tokens`, `operators`, `operator_sessions`, `host_events` tables; `hosts.enrollment_status`, `hosts.docker_enabled`, `hosts.credential_version` columns — consumed by Tasks 2–7.

- [ ] **Step 1: Write failing tests** — fresh-DB tables exist; legacy-DB backfill (`ENROLLED`/`false`); re-run idempotency; DavidLab-row survival (per `PHASE3B_MIGRATION_PLAN.md` §7).
- [ ] **Step 2:** `pytest backend/tests/test_migration.py -v` → FAIL (no alembic).
- [ ] **Step 3:** Init Alembic; autogenerate baseline; write `0002_phase3b` per migration plan §2; wire `upgrade_phase3b` into lifespan.
- [ ] **Step 4:** Tests PASS; full suite `pytest -q` still green (96 baseline).
- [ ] **Step 5:** Commit `feat: phase3b schema migration (additive-only)`.

### Task 2: Operator auth (sessions + login/logout/me)

**Files:**
- Create: `backend/app/api/operators.py`, `backend/app/services/operators.py`, password KDF in `core/security.py`
- Modify: `backend/app/main.py` (mount router), `backend/app/schemas/__init__.py`
- Test: `backend/tests/test_operator_auth.py`

**Interfaces:**
- Produces: `require_operator(role="ADMIN")` FastAPI dependency → returns `Operator`; `verify_operator_session(token) -> Operator | None`; `hash_operator_password`/`verify_operator_password` (PBKDF2, not the token hash).
- Consumes: `operators`, `operator_sessions` tables (Task 1).

- [ ] **Step 1: Failing tests** — login happy path; wrong password → 401; expired session → 401; logout idempotent; `require_operator` rejects missing/invalid token; VIEWER cannot call ADMIN endpoints (403 `OPERATOR_FORBIDDEN`).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement per `PHASE3B_API_CONTRACT.md` §2 (256-bit session tokens, hashed at rest, TTL 12h env-configurable, lazy purge).
- [ ] **Step 4:** PASS; suite green. Bootstrap a first ADMIN operator via CLI script (`backend/scripts/create_operator.py`), never via unauthenticated API.
- [ ] **Step 5:** Commit `feat: operator sessions and RBAC-ready auth`.

### Task 3: Bootstrap tokens + secure enroll

**Files:**
- Create: `backend/app/api/bootstrap_tokens.py`, `backend/app/services/enrollment.py`
- Modify: `backend/app/api/agents.py:31-45` (enroll), `backend/app/services/hosts.py:77-103` (enroll_host), `core/codes.py`
- Test: `backend/tests/test_bootstrap_enrollment.py`

**Interfaces:**
- Produces: `issue_bootstrap_token(db, operator, hostname, expires_in) -> (row, plaintext_once)`; `consume_bootstrap_token(db, token, hostname) -> row` (atomic single-use UPDATE); new enroll request field `bootstrap_token` (legacy `enrollment_token` accepted through transition, per contract §5.1).
- Consumes: `require_operator` (Task 2), `bootstrap_tokens` (Task 1).

- [ ] **Step 1: Failing tests** — token issued returns plaintext once, hash stored; enroll with valid token creates host + consumes token; **replay → 409**; **expired → 410**; revoked token → 401; token scoped to wrong hostname → 401; legacy `enrollment_token` path still works in transition; hostname-collision re-enroll of a REVOKED host now requires operator bootstrap (old silent un-revoke removed); concurrent identical enrollments → exactly one host row.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement: single-use consumption as atomic `UPDATE ... WHERE consumed_at IS NULL AND revoked_at IS NULL AND expires_at > ?` (SQLite rowcount gates); enrollment wrapped in one transaction with the host insert (`begin_nested` where nesting needed); audit events `BOOTSTRAP_ISSUED`/`BOOTSTRAP_CONSUMED` in `host_events`.
- [ ] **Step 4:** PASS; suite green.
- [ ] **Step 5:** Commit `feat: single-use bootstrap enrollment`.

### Task 4: Restart/recovery hardening

**Files:**
- Modify: `backend/app/services/deployments.py` (claim timeout), `backend/app/main.py` (background reconciler)
- Test: `backend/tests/test_recovery.py`

**Interfaces:**
- Produces: `reconcile_timed_out_ops(db, now) -> int` (re-queues RUNNING ops past `timeout_at`); env `NIMBUSOPS_OP_CLAIM_TIMEOUT_SECONDS` (default 600).
- Consumes: `deployment_operations.timeout_at` (Task 1).

- [ ] **Step 1: Failing tests** — op claimed then agent silent: after `timeout_at`, reconcile returns it to QUEUED and it re-polls; reconcile is idempotent; ops with results are never touched; restart mid-enrollment: bootstrap token + operator session survive (per Review Focus).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement reconciler (invoked from lifespan background task + lazily before `poll_commands`).
- [ ] **Step 4:** PASS; suite green.
- [ ] **Step 5:** Commit `feat: claim timeout and restart recovery`.

### Task 5: Revocation + rotation endpoints

**Files:**
- Create: `backend/app/api/host_lifecycle.py`, `backend/app/services/host_lifecycle.py`
- Modify: `backend/app/main.py`, `core/codes.py`
- Test: `backend/tests/test_host_lifecycle.py`

**Interfaces:**
- Produces: `POST /hosts/{id}/rotate-credential` (grace period via new `credential_version` + dual-hash check), `DELETE /hosts/{id}` (revoke-to-tombstone), `POST /hosts/{id}/re-enroll` (operator issues fresh bootstrap for existing host). Agent endpoints unchanged; `authenticate_host` gains expired-old-credential handling.
- Consumes: `require_operator` (Task 2), `host_events` (Task 1).

- [ ] **Step 1: Failing tests** — revoke → next heartbeat 401, host remains in `/hosts` with `REVOKED`, telemetry retained, tombstone never deleted; rotate → new token works, old token works within grace, old token 401 after grace; re-enroll of revoked host requires operator-issued bootstrap and restores `ENROLLED`; all three require ADMIN (VIEWER → 403); audit events written with actor.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement per contract §4; dual-hash grace window via `agent_token_hash` + `previous_token_hash`/`previous_expires_at` columns (additive).
- [ ] **Step 4:** PASS; suite green.
- [ ] **Step 5:** Commit `feat: credential rotation and safe revocation`.

### Task 6: Docker default-off + server-side sim rejection

**Files:**
- Modify: `backend/app/services/deployments.py` (`create_deployment`, `create_lifecycle_operation`), `backend/app/api/agents.py` (heartbeat response, poll filter), `backend/app/schemas/__init__.py`
- Test: `backend/tests/test_docker_authz.py`, update `backend/tests/test_deployments.py:312-318`

**Interfaces:**
- Produces: `HeartbeatResponse.docker_enabled`; `DOCKER_NOT_AUTHORIZED` 403 on Docker ops for disabled hosts; poll returns only ops whose Docker requirement is satisfied; `sim-` prefix rejection (400 `SIMULATED_HOST_REJECTED`) on `X-Host-Id` at router level.
- Consumes: `hosts.docker_enabled` (Task 1).

- [ ] **Step 1: Failing tests** — deploy to `docker_enabled=false` host → 403, no op row; after `PATCH hosts/{id} {docker_enabled:true}` → 202; heartbeat response carries `docker_enabled`; poll on disabled host yields no DEPLOY ops; **rewrite `test_unauthed_mutation_rejected`** to expect 401 without operator auth and 202 with it; `X-Host-Id: sim-…` → 400; `sim-` host_id in enroll body → 400.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement per contract §5.3/§6.
- [ ] **Step 4:** PASS; suite green — Phase 1/2 regression tests unchanged except the rewritten pin.
- [ ] **Step 5:** Commit `feat: docker default-off and server-side sim isolation`.

### Task 7: Frontend — Add Existing Server + Safe Unregister UX

**Files:**
- Modify: `frontend/src/api/client.ts` (new typed wrappers), `frontend/src/api/types.ts`, `frontend/src/views/Servers.tsx:39,42`, `frontend/src/views/ServerDetail.tsx`
- Test: `frontend/src/views/__tests__/servers.test.tsx`, new `enrollment.test.tsx`

**Interfaces:**
- Consumes: operator login endpoints, bootstrap-token endpoints, lifecycle endpoints (Tasks 2–6).
- Produces: `api.login/logout/me`, `api.issueBootstrapToken(hostname)`, `api.revokeHost(id)`, `api.rotateCredential(id)`, `api.patchHost(id, {docker_enabled})`; session token in memory only (never localStorage — per REACT-AUTH-001).

- [ ] **Step 1: Failing tests** — "Existing server" flow requires login first; bootstrap token displayed once with expiry countdown, copy button, one-time warning; enrolling host appears via poll; failure states (`409`/`410`/`401`/`503`) surfaced; Unregister dialog requires typing host_id, shows revoke consequences, never deletes history; simulated isolation untouched (`client.guard.test.ts` still passes; sim flows never call new endpoints).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement per architecture §2.6/§2.7; `docker_enabled` toggle on host detail with explicit confirmation.
- [ ] **Step 4:** PASS; `npm test` + `npm run build` green (45 baseline + new).
- [ ] **Step 5:** Commit `feat: operator enrollment and unregister UX`.

### Task 8: Docs + docs-driven verification

**Files:**
- Modify: `docs/API.md` (Phase 3B section), `docs/SECURITY.md` (updated model), `docs/README` links
- Test: none (docs)

- [ ] **Step 1:** Update docs to describe implemented state (mirror contracts; remove "NOT IMPLEMENTED" notes for delivered flows).
- [ ] **Step 2:** Full verification: `pytest -q`, `npm test`, `npm run build`, CI green; record results in a Phase 3B verification doc.
- [ ] **Step 3:** Commit `docs: phase3b implemented contracts`.

---

## Test Gate Summary (per mission "TEST PLANNING")

| Type | Coverage |
|---|---|
| Positive | Enroll via bootstrap; rotate within grace; reconcile re-queue; enable Docker then deploy |
| Negative | Unauthenticated mutations → 401; expired/replayed/revoked bootstrap tokens; wrong-scope token; revoked host heartbeat 401; sim-ID rejection |
| Adversarial | Revoke→re-enroll without operator token blocked; VIEWER privilege escalation blocked; hostname-collision abuse blocked |
| Concurrency | Two identical enrollments → one host; two bootstrap consumptions → one wins; duplicate deploy dedup preserved |
| Restart | Token/session/pending-op survival; reconciler idempotency; migration re-run |
| Rollback | Old code vs migrated DB (additive-only); DavidLab row byte-for-byte survival |

## Rollback Procedures

- Every task ships on `feat/phase3b-secure-enrollment`; each commit independently reverts (`git revert <sha>`) without schema reversal (additive-only migration, per `PHASE3B_MIGRATION_PLAN.md` §6).
- Feature-flag escape hatch: operator auth enforcement behind `NIMBUSOPS_REQUIRE_OPERATOR_AUTH` (default **on** after Task 6; flipping off restores Phase 2 trusted-local behavior for incident recovery **without** weakening tests — the flag default and the rewritten pin test keep the secure default honest).
