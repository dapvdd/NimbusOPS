# Phase 3B Release Review — Security & Release Readiness

Date: 2026-11-11 · Branch: `feat/phase3b-secure-enrollment` · Base: `main @ f9ae5de` · Review HEAD: `1c39e47` (+ fix `4f86067`)

Fresh-context adversarial review per the Phase 3B exit gate. Two independent passes:

- **Independent reviewer (fresh context, read-only subagent)**: endpoint enumeration, authz matrix, adversarial tracing, full test gates, diff hygiene.
- **Implementer self-review (this session)**: CORS preflight probe, guard-coverage comparison, logging redaction scan, TDD fix.

Findings are marked **[IND]** (independently verified) or **[SELF]** (self-review, consistent with independent pass).

## Verdict: CONDITIONAL APPROVE → resolved

The only Critical/Important regression (R-1, CORS methods) was fixed via TDD in `4f86067` and all gates re-run green. Remaining findings are Minor/Deferred and documented as known limitations (below). **Release is approved to proceed to push/PR upon owner approval** — no push or PR has been made.

## Findings

### Critical

None.

### Important

**R-1 [IND+SELF, CONFIRMED, FIXED in `4f86067`] — CORS `allow_methods` omitted PATCH/DELETE; every browser operator mutation failed preflight.**
- Evidence: `backend/app/main.py:79` (`["GET","POST"]`) vs Phase 3B browser calls `PATCH /api/v1/hosts/{id}` (docker enable), `DELETE /api/v1/hosts/{id}` (unregister), `DELETE /api/v1/operators/bootstrap-tokens/{id}` (`frontend/src/api/client.ts:172-180`).
- Reproduction: OPTIONS preflight with `Access-Control-Request-Method: PATCH|DELETE` → **400** (POST/GET → 200); pinned by `backend/tests/test_cors.py` (RED before fix: `PATCH preflight failed: 400`).
- Impact: in any cross-origin deployment, Docker enable, host revoke, and bootstrap-token revoke fail in the browser. Fail-closed (no security hole) — a functional regression of the Phase 3B feature set. Same-origin/proxy deployments (Vite dev proxy) were unaffected, which is why endpoint suites (TestClient does not enforce CORS on normal requests) masked it.
- Fix: allow_methods extended to `["GET","POST","PATCH","DELETE"]`; preflight tests pin all four methods pass, unknown origins still denied, wildcard-origin startup guard still raises.

### Minor

**R-2 [IND+SELF, CONFIRMED] — `_reject_simulated_host` missing on `POST /agents/telemetry`.** `backend/app/api/agents.py:99-107` (guard present on heartbeat L85, poll L128, result L148). No bypass found: a `sim-*` id is not in `hosts`, so `authenticate_host` 404s at `hosts.py:179`; browser-side `assertNotSimulated` also blocks the path (`client.ts:70-92`). Defense-in-depth inconsistency only. Report only (fix policy: non-regression).

**R-3 [IND, CONFIRMED] — Legacy shared-token path still rotates a live host's credential** (`hosts.py:88-123`, actor `agent`): anyone holding `NIMBUSOPS_ENROLLMENT_TOKEN` can re-enroll over an existing healthy host and replace its credential without operator involvement. Accepted by design O5 (transition), removal planned Phase 4. Mitigation present: revoked hosts can no longer be un-revoked this way (`hosts.py:90-95`). Report only.

**R-4 [IND, CONFIRMED] — No rate limiting on `/operators/login` (or enroll).** Brute-force feasible on exposed networks. Documented limitation (SECURITY.md; VERIFICATION.md defers to Phase 5). Deployment note: keep the control server inside the tailnet.

**R-5 [IND, CONFIRMED] — Reconciler audit noise on claim race:** `deployments.py:70-79` logs `REQUEUED_TIMEOUT` events for every stale id even when the guarded UPDATE lost the race (`rowcount < len(stale_ids)`). Audit trail may over-count; no state damage.

**R-6 [IND, CONFIRMED] — No security headers (CSP, X-Frame-Options, nosniff) set by the backend for the SPA.** `main.py:60-91`. Acceptable for tailnet-only serving; revisit if exposed via edge/CDN.

**R-7 [IND, CONFIRMED] — Expired operator sessions and consumed/expired bootstrap token rows are never purged** (`operators.py:50`, `enrollment.py`). Unbounded growth; recommend a retention sweep in Phase 4.

### Deferred (carried from prior review; non-blocking)

- **D-1** Crash window in bootstrap backfill: token consumed+committed (`enrollment.py:118`) before host insert/`consumed_by` backfill (`agents.py:41-46`); a crash between the two burns the token without a host link. Audit trail still shows the consumption; operator can issue a new token. Consider fusing into one transaction in Phase 4.
- **D-2** Per-boot full-table `UPDATE hosts SET col=default WHERE col IS NULL` (`migrations.py:136-138`) — fine at current scale; index-friendly batching later.
- **D-3** `applications.py:99,111` reach into private `svc._get_deployment_or_404` — style; promote to public helper.

### NITs

- Token pepper falls back to enrollment token, else empty constant key (`security.py:34-35`) — acceptable because agent/session/bootstrap tokens are 256-bit random; noted for Phase 4 config hygiene.
- `issue_bootstrap_token` strips hostname but `EnrollRequest` does not (`enrollment.py:55` vs `schemas/__init__.py:11`) — whitespace mismatch yields 401 instead of a match; cosmetic.

(Continued in Part 2: endpoint classification, migration assessment, test results, deployment blockers.)

## Endpoint classification (scope item 1)

| Class | Endpoints |
| --- | --- |
| Public | `GET /api/v1/health`; `GET /api/v1/hosts`; `GET /api/v1/hosts/{id}`; `GET /api/v1/hosts/{id}/metrics`; `GET /api/v1/templates`; `GET /api/v1/applications`; `GET /api/v1/applications/{id}/container-state`; `GET /api/v1/operations/{id}`; `POST /api/v1/agents/enroll`; `POST /api/v1/operators/login`; `POST /api/v1/operators/logout` (idempotent, tolerates no/unknown token) |
| Agent-authenticated (X-Host-Id + Bearer agent token, host-bound) | `POST /api/v1/agents/heartbeat`; `POST /api/v1/agents/telemetry`; `POST /api/v1/agents/commands/poll`; `POST /api/v1/agents/commands/{id}/result` |
| Operator-authenticated (any role) | `GET /api/v1/operators/me` |
| ADMIN-only | `POST` + `GET /api/v1/operators/bootstrap-tokens`; `DELETE /api/v1/operators/bootstrap-tokens/{id}`; `PATCH /api/v1/hosts/{id}`; `POST /api/v1/hosts/{id}/rotate-credential`; `DELETE /api/v1/hosts/{id}`; `POST /api/v1/hosts/{id}/re-enroll`; `POST /api/v1/applications/deploy`; `POST /api/v1/applications/{id}/start`; `POST /api/v1/applications/{id}/stop` |
| VIEWER-readable | All public reads above are deliberately unauthenticated (SECURITY.md limitation 9). VIEWER role gets 403 `OPERATOR_FORBIDDEN` on every ADMIN row above; no VIEWER-scoped privileged reads exist in Phase 3B (Phase 5). |

Unauthenticated reads expose host inventory, metrics, deployment and operation state — **known, documented** (trusted-local / tailnet model; STAGE_A audit risk #7; VERIFICATION gap "authed reads Phase 5").

## Authz & credential-separation verification (scope items 2-6)

- Every infrastructure-mutating endpoint carries `require_operator(role="ADMIN")` (`bootstrap_tokens.py:52,70,94`; `host_lifecycle.py:69,88,102,113`; `applications.py:85,96,109`) — verified by route table above; no POST/PATCH/DELETE route lacks a dependency.
- Agent vs operator credentials are disjoint: agent tokens hash-checked against `hosts.agent_token_hash`; operator sessions against `operator_sessions.token_hash`; no cross-lookup path found. Cross-host impersonation blocked: poll filters `host_id == X-Host-Id` (`deployments.py:290`), `submit_result` rejects foreign ops 403 (`deployments.py:337-338`).
- Bootstrap tokens: hostname scope checked **before** consumption so a wrong-host attempt never burns the token (`enrollment.py:96-97`); consumption is a single guarded atomic UPDATE (`enrollment.py:99-109`); replay → 409, expired → 410, revoked/wrong-host/unknown → 401. Concurrency: exactly one winner by rowcount (`enrollment.py:110-117`).
- Passwords: PBKDF2-SHA256 240k iterations (`security.py:54-62`); sessions hashed at rest, TTL 12h enforced at verification, logout revokes (`operators.py:39-55,89-101`). No token/password material in any log line (grep-verified; audit details are hostname/id only).
- Rotation grace: dual-hash window (`hosts.py:182-198`); grace expiry clears the stale hash lazily; revoke kills the grace window (`host_lifecycle.py:52-53`); revoked hosts 401 on all agent routes (`hosts.py:180-181`).

## Reconciler & recovery (scope item 8)

Restart recovery (ops re-claimable after restart), duplicate-claim protection (atomic `WHERE status='QUEUED'` claim, `deployments.py:301-306`), revoked/rotated hosts (ops host-bound; results host-checked), stale RUNNING requeue (`deployments.py:42-82`), idempotent second pass (returns 0). Audit-noise caveat in R-5.

## Migration & compatibility assessment (scope item 9)

`backend/app/core/migrations.py` (O7 deviation documented: hand-written, Alembic deferred to Phase 4):

- **Additive-only**: 4 new tables, 6 new host columns with constant defaults, 1 op column, 2 indexes; no rename/drop/type change/row deletion (`_NEW_TABLES`, `_NEW_HOST_COLUMNS`, `_NEW_OP_COLUMNS`).
- **Existing-DB compatible**: legacy DavidLab row survives with id + credential byte-identical; only 3 backfilled column values are written (pinned by `test_migration.py` legacy upgrade test).
- **Repeat-safe**: `IF NOT EXISTS` everywhere + per-column membership check + version marker row; double-run test passes.
- **Transactions**: runs in one `eng.begin()` block (SQLite DDL is transactional); idempotent re-run is the **rollback strategy** — there is no down-migration (documented; acceptable for additive schema, flag for Alembic in Phase 4).

## Test results (scope item 13)

| Gate | Command | Before review | After fix `4f86067` |
| --- | --- | --- | --- |
| Backend | `.venv/Scripts/python -m pytest -q` | 150 passed | **153 passed** (150 + 3 CORS tests) |
| Frontend | `npm.cmd test` (frontend/) | 51 passed | **51 passed** |
| Frontend build | `npm.cmd run build` | green | **green** |

Reviewer independently reproduced the pre-fix gates: pytest 150 passed, npm 51 passed, build green. Exit codes 0.

## Diff hygiene (scope item 14)

`git diff f9ae5de..1c39e47 --stat`: 44 files, all Phase 3B scope (backend app/tests, frontend client/views/tests, docs, .env.example). The 4 untracked files (`docs/NIMBUSOPS_DEMO_READY.md`, `docs/NIMBUSOPS_DEMO_RESULTS.md`, `docs/STAGE_A_DAVIDLAB_AUDIT.md`, `frontend/src/lib/format.test.ts`) remain untracked and untouched — not part of the branch. No unrelated modifications.

## Changes made during this review

| Commit | Change |
| --- | --- |
| `4f86067` | R-1 fix: CORS allow_methods + `backend/tests/test_cors.py` (TDD RED→GREEN); gates re-run green (153/51/build). |

No other code changes. R-2..R-7, D-1..D-3, NITs: report only, per fix policy (no Critical/Important regression among them).

## Remaining deployment blockers / preconditions

1. **Run behind Tailscale/VPN as documented** — unauthenticated reads + no rate limiting (R-4, R-6) make public internet exposure unsafe. TLS terminates at the tailnet boundary.
2. `NIMBUSOPS_ENROLLMENT_TOKEN` should be unset/empty in deployments that only use bootstrap enrollment, shrinking legacy-path exposure (R-3) until Phase 4 removes it.
3. First ADMIN must be created out-of-band via `backend/scripts/create_operator.py` (documented; never via HTTP).
4. Alembic wiring (O7) is Phase 4; until then `upgrade_phase3b()` runs at startup by design.

## Release verdict

**CONDITIONAL APPROVE — conditions met; proceed.**

Rationale: one Important regression found (R-1 CORS methods) was the only Critical/Important finding across both independent and self-review passes; it is fixed via TDD with regression tests, and all gates re-run green. All remaining findings are Minor/Deferred with documented mitigations and Phase 4/5 owners. Codebase otherwise passed adversarial review: no privilege-escalation, replay, cross-host, or un-revoke path found; secrets handling and audit trail are sound; migration is DavidLab-safe.

**Next step (requires owner approval): push `feat/phase3b-secure-enrollment` to origin and open the PR. Nothing has been pushed.**

