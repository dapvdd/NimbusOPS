# Phase 3B — Final Acceptance

Date: 2026-11-12 · Baseline main: `9902667` · Branch: `feat/autonomous-phase4-6`
Scope: formal consolidation of Phase 3B (secure enrollment + operator credential
lifecycle) acceptance evidence: automated gates, live validation, threat-model
closure, and residual limitations.

## 1. Decisions delivered (O1–O8)

| Decision | Delivered | Evidence |
| --- | --- | --- |
| O1 operator auth | Session bearer tokens (256-bit, hashed at rest, 12 h TTL), ADMIN/VIEWER roles, login/logout/me; token memory-only in frontend | `test_operator_auth.py` (9), `test_phase3b_acceptance_gaps.py` (malformed header/logins) |
| O2 bootstrap delivery | Single-use token shown once + copy + countdown; operator pastes to agent env | `test_bootstrap_enrollment.py` (16), enrollment UI tests |
| O3 credential lifetime | Permanent until operator revoke/rotate | `test_host_lifecycle.py` (9) |
| O4 rotation grace | 5 min default (env-configurable), dual-hash check | `test_host_lifecycle.py` rotate tests |
| O5 legacy compat | `NIMBUSOPS_ENROLLMENT_TOKEN` accepted in transition; silent un-revoke removed | `test_bootstrap_enrollment.py` legacy path |
| O6 DavidLab migration | Additive idempotent startup migration; backfill ENROLLED/docker-off/cred-v1; legacy credential survives | `test_migration.py` (4) + live staging validation (below) |
| O7 migrations | Hand-written idempotent `upgrade_phase3b()` (Alembic deferred to Phase 4+; deviation recorded in ledger) | `core/migrations.py`, marker table |
| O8 audit | Append-only `host_events` + legacy `enrollment_audit` | lifecycle/bootstrap suites |

## 2. Automated gates (this branch, 2026-11-12)

| Gate | Command | Result |
| --- | --- | --- |
| Full backend suite | `python -m pytest -q` | **161 passed** (153 baseline + 8 new acceptance-gap tests) |
| Frontend suite | `npm test` | 42 passed (worktree baseline; 51 on main incl. untracked local test) |
| Frontend build | `npm run build` | green (see Task 5/8 logs on branch) |

New coverage closing acceptance gaps:

- Malformed Authorization: missing Bearer scheme → 401 (previously accepted raw —
  fixed), empty token → 401, oversized (4 KiB) → 401, latin-1-escaped garbage → 401.
- Malformed login JSON: missing password / wrong types → 422; unknown user → 401
  (no enumeration).
- Bootstrap concurrency (AC-11 pattern): 32 parallel redemptions → exactly one
  200, remainder 409; single host created.

## 3. Live validation evidence (2026-11-11/12, reused per program instructions)

| Scenario | Result |
| --- | --- |
| Staging snapshot via SQLite online backup API | PASS — source SHA unchanged (`a598a9e6…`) |
| Phase 3B migration on staging clone | PASS — 4 tables + marker, backfill verified, integrity ok |
| Loopback-only backend bind (127.0.0.1:8010) | PASS — `Get-NetTCPConnection` verified |
| Loopback-only SSH reverse tunnel (127.0.0.1:8000 remote) | PASS — `ss` verified; `GatewayPorts no` |
| Orphaned DavidLab agent natural reconnect (no restart) | PASS — ONLINE within ~60 s |
| Connectivity stability window | PASS — 375/375 requests 200 OK over 185 s |
| Zero Docker operations dispatched | PASS — 0 ops claimed; `docker_enabled=0` enforced |
| Production database integrity | PASS — SHA unchanged pre/post migration |
| SPECTRA / demo containers / DCC | PASS — untouched throughout (`Up 2 days` readings) |

## 4. Security posture summary

- All application mutations require operator session (AC-01 pin test rewritten
  and green); reads stay public per accepted trusted-local threat model.
- Docker default-off per host, server-side enforced (`403 DOCKER_NOT_AUTHORIZED`).
- Tokens: keyed SHA-256 at rest, pepper via env; never logged; bootstrap tokens
  single-use, TTL ≤ 1 h, hostname-scoped.
- Operator passwords: PBKDF2-SHA256 (240k iters), constant-time verify.
- Rate limiting on login: **Phase 6 scope** (documented limitation until then).

## 5. Residual limitations (explicit)

1. Alembic wiring deferred (O7 deviation) — `upgrade_phase3b()` is the live path.
2. Login rate limiting — delivered in Phase 6 (this program).
3. Operator-authenticated reads / cookie sessions — Phase 5 roadmap, deferred.
4. Non-ASCII Authorization header test impractical over httpx transport —
   latin-1-escaped variant covers the rejection path.

## 6. Verdict

**Phase 3B: ACCEPTED** (conditional items resolved; minors tracked to Phase 5/6
workstreams in this program).
