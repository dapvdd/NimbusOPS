# Phase 3B Verification — Secure Real-Host Enrollment

Date: 2026-11-10 · Branch: `feat/phase3b-secure-enrollment` · Executor: inline
(executing-plans + TDD; every task watched RED before GREEN; ledger in
`.superpowers/sdd/PHASE3B_IMPLEMENTATION_PLAN.md/progress.md`).

## Scope implemented (O1–O8 all delivered)

| Decision | Delivered as |
| --- | --- |
| O1 operator auth | Session Bearer tokens (256-bit, hashed at rest, TTL 12 h env-configurable), ADMIN/VIEWER roles, login/logout/me; frontend stores in memory only |
| O2 bootstrap delivery | Token shown once in dashboard with copy + expiry countdown; operator pastes into agent env |
| O3 credential lifetime | Permanent until operator revoke/rotate |
| O4 rotation grace | 5 min default, env-configurable, dual-hash check |
| O5 legacy compatibility | `NIMBUSOPS_ENROLLMENT_TOKEN` accepted through transition; silent un-revoke removed |
| O6 DavidLab migration | Additive idempotent startup migration: `enrollment_status='ENROLLED'`, `docker_enabled=0`, `credential_version=1`; existing credential keeps working (byte-for-byte row survival test) |
| O7 migrations | Intended Alembic; implemented as the hand-written idempotent `upgrade_phase3b()` run at startup (deviation recorded in ledger; Alembic wiring remains Phase 4 work) |
| O8 audit | Append-only `host_events` (event/actor/detail) alongside legacy `enrollment_audit` |

## Test gates (all green on this machine)

| Gate | Command | Result |
| --- | --- | --- |
| Backend suite | `.venv/Scripts/python -m pytest -q` | **150 passed** (baseline 96 + 54 new) |
| Agent/backend integration | included in pytest run (`backend/tests_integration`) | 7 passed (within the 150) |
| Frontend | `npm test` | **51 passed** (baseline 45 + 6 new) |
| Frontend build | `npm run build` | green (`tsc -b && vite build`) |

Exit codes verified `0` for all three gates.

## New backend coverage by task

- Task 1 (`test_migration.py`, 4): fresh-DB structures; host defaults;
  legacy-DB in-place upgrade with david-lab-like row survival + pre-3B token
  path intact; idempotent double-run.
- Task 2 (`test_operator_auth.py`, 9 + `test_create_operator_script.py`, 3):
  login happy/wrong-password/unknown-user (no enumeration); expired session;
  logout idempotent; RBAC probe (`OPERATOR_FORBIDDEN`); token hashed at rest;
  CLI get-or-create + duplicate rejection.
- Task 3 (`test_bootstrap_enrollment.py`, 16): issue-once + hash-only
  storage; ADMIN-only issue; consume→host creation (ENROLLED, docker off);
  replay 409; expired 410; revoked 401; wrong-hostname 401; unknown 401;
  legacy path (O5); REVOKED-host legacy re-take blocked (409) but operator
  bootstrap restores it; concurrent identical enrollments → exactly one host;
  list without token material; revoke idempotent; consumed revoke → 409.
- Task 4 (`test_recovery.py`, 4): timed-out RUNNING op re-queued + re-claimed
  with fresh deadline; reconciler idempotent and gentle to fresh claims;
  terminal ops never touched; bootstrap tokens + operator sessions survive a
  full app restart.
- Task 5 (`test_host_lifecycle.py`, 9): revoke blocks agent (401
  `HOST_REVOKED`), tombstone + telemetry retained, idempotent, listed as
  REVOKED; rotate: new token immediate, old within grace, dead after; rotate
  on revoked → 409; re-enroll bootstrap restores host only upon agent
  consumption (identity UUID stable); all ADMIN-only; audit events with
  actor; public `HostOut` carries `enrollment_status`/`docker_enabled`.
- Task 6 (`test_docker_authz.py`, 9 + rewritten pin in
  `test_deployments.py`): deploy to docker-disabled host → 403
  `DOCKER_NOT_AUTHORIZED`, zero op rows; enable via PATCH → 202; start/stop
  blocked likewise; heartbeat carries `docker_enabled`; poll on disabled
  host does not claim DEPLOY ops (stays QUEUED, deliverable after enable);
  server-side `sim-` rejection on heartbeat/poll/result and enroll; rewritten
  `test_unauthed_mutation_rejected` (401 without session, 202 with —
  AC-01); VIEWER cannot mutate (403 before Docker check).

## Frontend coverage (Task 7)

- Existing-server flow requires login before any token UI (rewritten pin).
- Full flow: login → issue → token shown once + copy + countdown + one-time
  warning; agent appears via poll after enrollment (poll semantics unchanged).
- 401 invalid credentials surfaced, stays on login; 410 surfaced.
- Session token never persisted (localStorage asserted empty).
- Unregister dialog: consequence list, typed host-id confirmation, history
  retention stated, button disabled until exact id typed.
- Simulated isolation untouched: `client.guard.test.ts` still green; sim
  flows issue no operator/lifecycle calls (asserted).

## Security-relevant behavior changes (deploy notes)

- Application mutations now require an operator session: demo scripts or
  curl flows that deploy without logging in will receive
  `401 OPERATOR_AUTH_REQUIRED` (this is the intended AC-01 gate; the Phase 2
  pin test was rewritten accordingly, with user approval).
- Docker is default-off per host (incl. migrated DavidLab): enable explicitly
  via `PATCH /api/v1/hosts/{id}` by an ADMIN.
- Create the first operator out-of-band:
  `backend/.venv/Scripts/python -m backend.scripts.create_operator --username admin`.
- No push / PR / merge / deploy was performed; no SSH into DavidLab; no
  Docker/systemd/firewall/SPECTRA changes (per mission constraints).

## Known gaps / deferred

- Alembic wiring (O7 deviation): `upgrade_phase3b()` is idempotent and
  marker-recorded; converting it to Alembic revisions is Phase 4 work.
- Rate limiting on login/enroll (limitation 6) — Phase 4.
- Operator-authenticated reads + cookie variant (O1 note) — Phase 5.
