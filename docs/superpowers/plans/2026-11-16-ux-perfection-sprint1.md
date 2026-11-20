# NimbusOps UX Perfection Sprint 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a zero-friction enrollment wizard, truthful host lifecycle UX, persistent service visibility, a single actionable dashboard, and a small design system. Every control calls a real authorized backend operation; every state is the backend's state.

**Architecture:** Backend adds `effective_status`, `agent_mode`, bootstrap-token intent guards (issue + consumption), one-active-token uniqueness, and a host-events read endpoint. Agent gains `--reenroll` and `--apply-credential-file` one-shot flags with backup/restore and a verified heartbeat. Frontend removes the simulation registry, rewrites fleet/onboarding/lifecycle views, and ships a design system. Seven reviewable commits on `sprint/ux-perfection`; CI stays green throughout.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy / SQLite (WAL), React 18 + Vite + Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-11-16-ux-perfection-sprint-1-design.md` (commit `532f1cd`) — the plan argues from the spec; executors read both.

## Global Constraints

- Never expose credentials, tokens, cookies, or secrets in any document, log, or test.
- Never delete/reset databases; never modify live deployments without explicit approval.
- Preserve API compatibility: legacy `GET /hosts` shape unchanged; additive migrations only.
- Bootstrap/rotation tokens reach the host via a 0600 file typed at a prompt; generated commands contain no token and no `--token`.
- `REVOKED` is terminal; never display it as offline; never retry with the revoked credential.
- VIEWER sees no lifecycle/enrollment/deployment/Docker controls (absent, not disabled).
- Destructive actions: ADMIN + typed confirmation; revoke requires typing the hostname.
- Each slice is exactly one commit on `sprint/ux-perfection`; no push/merge/deploy without approval.
- Per-commit gates: `.venv\Scripts\python -m pytest -q` AND `npm test` AND `npx tsc -b` AND `npx vite build` (from repo root, worktree `C:\Users\user\.local\share\opencode\worktree\2bef8e\sprint-ux-perfection`).

## Review Focus

- A revoked host with a fresh heartbeat renders ONLINE today; `effective_status` must win over connectivity in every consumer (test: `test_effective_status.py`, slice 1).
- Rejected bootstrap consumption must never burn the token (intent/hostname checks run before the consuming UPDATE; test: `test_bootstrap_intent.py`, slice 1).
- The StatusBadge must fail closed on unknown status values (fallback ships with the union widening; test: `StatusBadge` cases in `views.test.tsx`, slice 1).
- One-shot `--reenroll` must not report success before a verified heartbeat (test: `test_agent_reenroll.py`, slice 2).
- Removing the legacy bearer path must not break signed-in cookie sessions (test: `docker.host.test.tsx` rewrite, slice 3).
- Deleting the sim registry must leave no view importing it (grep gate + full `npm test`, slice 7).

---

## Slice 1 — Backend: effective status, agent mode, lifecycle guards

**Commit:** `feat(backend): effective host status, agent mode, and lifecycle guards`
**Owns tests:** all new backend tests; `test_migration.py` docstring fix; `test_rc2_enrollment_contract.py` intent fix. Frontend touch is limited to `api/types.ts` (widen `HostStatus`) + `components/StatusBadge.tsx` (defensive fallback) + their tests.

### Task 1.1: `effective_status` in `services/hosts.py`

**Files:**
- Modify: `backend/app/services/hosts.py` (after `compute_status`, ~line 59)
- Test: `backend/tests/test_effective_status.py` (new)

**Interfaces:**
- Produces: `effective_status(*, is_revoked: bool, enrollment_status: str, last_seen_at: datetime | None, now: datetime, stale_s: int, offline_s: int) -> str` — returns `"REVOKED"` when `is_revoked or enrollment_status == "REVOKED"`, else delegates to `compute_status(last_seen_at, now, stale_s, offline_s)`.
- Consumes: existing `compute_status` (unchanged signature).

- [ ] **Step 1: Write failing tests** in `test_effective_status.py`:
  - `test_revoked_beats_fresh_heartbeat`: `is_revoked=True`, `last_seen_at=now` -> `"REVOKED"`.
  - `test_enrollment_status_revoked_wins`: `is_revoked=False, enrollment_status="REVOKED"` -> `"REVOKED"`.
  - `test_non_revoked_unchanged`: parametrize over (`last_seen_at=None` -> OFFLINE, fresh -> ONLINE, mid-age -> STALE, past-window -> OFFLINE) matching `compute_status` semantics.
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest backend/tests/test_effective_status.py -q` — expect FAIL (ImportError: cannot import name `effective_status`).
- [ ] **Step 3: Implement** the function exactly as the signature above (3-line body; delegate to `compute_status`).
- [ ] **Step 4: Run** again — expect PASS.
- [ ] **Step 5: Commit** only after the whole slice-1 test suite is green (see Task 1.9); intermediate commits within the slice are allowed but the slice commit is the deliverable.

### Task 1.2: Model columns + migration

**Files:**
- Modify: `backend/app/models/__init__.py` (`Host`, `BootstrapToken`)
- Modify: `backend/app/core/migrations.py` (additive migration function)
- Test: extend `backend/tests/test_migration.py`

**Interfaces:**
- Produces: `Host.agent_mode: str | None` (nullable, no default); `BootstrapToken.intent: str` (default `"enroll"`, values `enroll|reenroll`); partial unique index `uq_bootstrap_tokens_active_hostname` on `bootstrap_tokens(hostname)` WHERE `consumed_at IS NULL AND revoked_at IS NULL`.
- Migration behavior: additive `ALTER TABLE ... ADD COLUMN`; no backfill (legacy `agent_mode` = NULL = "not reported", legacy `intent` = `enroll`); index creation wrapped in try/except that logs a warning and skips on failure (legacy duplicate hostnames), mirroring the existing in-flight-operation index pattern.

- [ ] **Step 1: Failing test** in `test_migration.py`: new host row has `agent_mode IS NULL`; new bootstrap token defaults `intent='enroll'`; creating the index twice is idempotent; a legacy DB with two active tokens for one hostname still starts (warning, no index) and existing rows are untouched.
- [ ] **Step 2: Run** — expect FAIL (no such columns).
- [ ] **Step 3: Implement** columns + migration (follow the file's existing additive-column pattern; fail-safe index skip).
- [ ] **Step 4: Run** `test_migration.py` — PASS.

### Task 1.3: `HostOut` widening + schema changes

**Files:**
- Modify: `backend/app/schemas/__init__.py` (`HostOut` ~line 121, `HeartbeatRequest`, `HostPatchRequest`, bootstrap-token request)
- Test: extend `backend/tests/test_hosts_telemetry.py`

**Interfaces:**
- Produces on `HostOut`: `status: "ONLINE|STALE|OFFLINE|REVOKED"` (widened literal), `connectivity: "ONLINE|STALE|OFFLINE"`, `agent_mode: "executor|telemetry-only|null"`, `credential_version: int`, `credential_grace_until: datetime | None` (null unless `previous_token_hash` set AND `previous_token_expires_at > now`).
- Produces on `HeartbeatRequest`: `agent_mode: Literal["executor","telemetry-only"] | None = None` (explicit None clears).
- Produces on `HostPatchRequest`: `environment: Literal["PRIVATE","PUBLIC-CLOUD"] | None`.
- Produces on bootstrap-token create: `intent: Literal["enroll","reenroll"] = "enroll"`.

- [ ] **Step 1: Failing test** — `GET /api/v1/hosts/{id}` response contains all five new fields; a heartbeat with `agent_mode="executor"` persists it; a heartbeat without the field clears it to null; `credential_grace_until` is null for a host that never rotated and non-null for one inside its grace window.
- [ ] **Step 2: Run** — FAIL (missing fields).
- [ ] **Step 3: Implement** schema changes + populate in `api/public.py` (`get_host` and `list_hosts` both) + `agent_mode` write in `touch_heartbeat` (write the reported value **including None** — do not skip falsy).
- [ ] **Step 4: Run** — PASS.

### Task 1.4: Bootstrap-token intent guards

**Files:**
- Modify: `backend/app/core/codes.py` (add `BOOTSTRAP_TOKEN_ACTIVE`, `BOOTSTRAP_TOKEN_HOSTNAME_MISMATCH`)
- Modify: `backend/app/services/enrollment.py` (`issue_bootstrap_token`, `consume_bootstrap_token`)
- Modify: `backend/app/api/bootstrap_tokens.py` (`intent` in request, `?active=true&limit=` on list)
- Test: `backend/tests/test_bootstrap_intent.py` (new)

**Interfaces:**
- `issue_bootstrap_token(db, operator, hostname, expires_in_seconds=600, *, intent: str = "enroll") -> tuple[BootstrapToken, str]` — normalizes hostname via `hostname.strip().lower()`; revokes expired active tokens for the hostname before insert; raises `409 BOOTSTRAP_TOKEN_ACTIVE` (via `IntegrityError` catch on the partial unique index) when another active token exists.
- `consume_bootstrap_token(db, token, hostname, commit=True) -> BootstrapToken` — normalizes hostname; **before the consuming UPDATE**: mismatched hostname → `401 BOOTSTRAP_TOKEN_HOSTNAME_MISMATCH` (message contains expected vs actual, never the token); `intent="enroll"` + hostname exists (including revoked) → `409 HOSTNAME_TAKEN`; `intent="reenroll"` + hostname absent → `404 HOST_NOT_FOUND`. These checks run before the UPDATE so a rejected attempt never burns the token.
- List endpoint: `?active=true` filters to `consumed_at IS NULL AND revoked_at IS NULL AND expires_at > now`; `?limit=` caps rows (default 50, max 200).

- [ ] **Step 1: Failing tests** in `test_bootstrap_intent.py`:
  - `test_enroll_intent_rejects_existing_hostname` (fresh + revoked host).
  - `test_reenroll_intent_requires_existing_hostname`.
  - `test_hostname_normalization_matches` (issue `Host-1`, consume `host-1`).
  - `test_mismatch_reports_expected_vs_actual_without_burning` (consume again with correct hostname succeeds).
  - `test_second_active_token_returns_bootstrap_token_active`; revoke first, reissue succeeds.
  - `test_expired_active_token_revoked_on_issue` (expired active token no longer blocks).
  - `test_active_filter_and_limit_on_list`.
  - `test_issue_default_intent_is_enroll` (legacy callers unaffected).
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** the guards; keep the hostname check and intent check ahead of the UPDATE inside the same transaction that later creates/restores the host.
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Fix dependents**: `test_rc2_enrollment_contract.py::test_bootstrap_reenroll_rotates_with_stable_identity` issues its second token without intent → update `_issue` to pass `intent="reenroll"` (same as the console's re-enroll dialog). `test_migration.py` docstring: change "defaults to PENDING" wording to "docker disabled; enrollment completes as ENROLLED" (assertion at line 47 already expects ENROLLED; assertion text unchanged).

### Task 1.5: Host events endpoint + environment PATCH

**Files:**
- Modify: `backend/app/api/host_lifecycle.py` (add `GET /{host_id}/events?limit=`; add environment to PATCH)
- Modify: `backend/app/services/host_lifecycle.py` (add `set_environment(db, host_id, actor, environment)`)
- Modify: `backend/app/main.py` (mount events route on the read-protected router or add `Depends(operators.require_read)` on the events endpoint — events live on `host_lifecycle.router`, which is NOT read-protected today, so the events route needs the dependency explicitly)
- Modify: `backend/tests/conftest.py` — add the new test module to the `authenticated_reads` `read_modules` set
- Test: `backend/tests/test_host_events.py` (new)

**Interfaces:**
- Produces: `GET /api/v1/hosts/{id}/events?limit=` → `{"events": [{"id","host_id","event","actor","detail","created_at"}], "count"}` newest-first; VIEWER-readable; no token material in `detail`.
- Produces: `set_environment` validates `Literal["PRIVATE","PUBLIC-CLOUD"]`, writes `Host.environment`, records `HostEvent(event="ENVIRONMENT_CHANGED", actor=op.username, detail=f"old={old} new={new}")`.
- PATCH `{"environment": ...}` returns the updated `HostOut`.

- [ ] **Step 1: Failing tests** in `test_host_events.py`:
  - `test_events_newest_first_and_limit` (enroll → rotate → revoke; assert order + `?limit=2`).
  - `test_events_readable_by_viewer_and_requires_auth` (401 without session).
  - `test_events_contain_no_token_material` (rotate first, then assert no 64-char token substring in any `detail`).
  - `test_patch_environment_admin_ok_viewer_403_invalid_422` (+ `ENVIRONMENT_CHANGED` event appended with old/new value).
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** endpoint + service; register the test module in `authenticated_reads`.
- [ ] **Step 4: Run** — PASS.

### Task 1.6: Enrollment event flush for fresh hosts

**Files:**
- Modify: `backend/app/services/hosts.py` (`enroll_host` new-host branch ~line 129)
- Test: extend `test_hosts_telemetry.py`

- [ ] **Step 1: Failing test**: enroll a fresh host, immediately `GET /api/v1/hosts/{id}/events` → contains `ENROLLED`. (Today the event row can precede the host row's flush; the endpoint joins on host id, so the fix is `db.flush()` on the new `Host` before `record_host_event`.)
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement**: add `db.flush()` (or `db.commit()` ordering) so the host row exists before the event insert.
- [ ] **Step 4: Run** — PASS.

### Task 1.7: Frontend contract guard (slice-1's only UI touch)

**Files:**
- Modify: `frontend/src/api/types.ts` (`HostStatus` gains `"REVOKED"`)
- Modify: `frontend/src/components/StatusBadge.tsx` (defensive fallback)
- Test: `frontend/src/views/__tests__/views.test.tsx` (add cases)

- [ ] **Step 1: Failing test**: render `<StatusBadge status={"REVOKED" as HostStatus} />` — expect no crash and a visible "Unknown"/fallback label (today it throws on `STATUS_META[status].bg`).
- [ ] **Step 2: Run** `npx vitest run src/views/__tests__/views.test.tsx` — FAIL (crash).
- [ ] **Step 3: Implement**: `const meta = STATUS_META[status] ?? { label: "Unknown", dot: "bg-ink-500", text: "text-ink-300", bg: "bg-ink-800 border-ink-600" };` and widen the `STATUS_META` type to `Record<HostStatus, ...> | Record<string, ...>`.
- [ ] **Step 4: Run** — PASS.

### Task 1.8: docs/API.md

- [ ] **Step 1**: Document the widened `status` literal, new `HostOut` fields, `intent` on token issue, `?active&limit`, `GET /hosts/{id}/events`, PATCH `environment`, and the agent heartbeat `agent_mode` field (additive; older agents unaffected).

### Task 1.9: Full gates + slice commit

- [ ] **Step 1**: `.venv\Scripts\python -m pytest -q` — expect ~296+ passed, 1 skipped (287 baseline + new).
- [ ] **Step 2**: `cd frontend; npm test` — 58+ passed; `npx tsc -b`; `npx vite build` — clean.
- [ ] **Step 3**: `git add` the slice files + `git commit -m "feat(backend): effective host status, agent mode, and lifecycle guards"`.

---

## Slice 2 — Agent: one-shot re-enroll and credential-file application

**Commit:** `feat(agent): one-shot re-enroll and credential-file application`

### Task 2.1: `--reenroll` flag

**Files:**
- Modify: `agent/nimbusops_agent/main.py` (argparse + a `run_reenroll()` one-shot path before `ensure_enrolled()`'s early return at line 46)
- Modify: `agent/nimbusops_agent/config.py` (backup/restore helpers if not already present)
- Test: `agent/tests/test_reenroll.py` (new)

**Interfaces:**
- Produces: `run_reenroll(state_path: Path, token: str, server_url: str, agent_mode: str | None) -> int` — exit codes: `0` identity saved AND one heartbeat verified with the new credential; `2` any failure (identity restored from backup; backup kept on restore); never enters the monitoring loop.
- Behavior: requires a **bootstrap** token (file path via `--bootstrap-token-file` or `NIMBUSOPS_AGENT_BOOTSTRAP_TOKEN_FILE`; a legacy `enrollment_token` is rejected with exit 2 + a clear message); backs up `agent.json` → `agent.json.pre-reenroll-<utc>` with 0600 before touching anything; writes the new identity through the existing atomic `save_identity` (fsync + `os.replace`); deletes the backup only after the verified heartbeat; stderr messages never contain the token.

- [ ] **Step 1: Failing tests** in `test_reenroll.py` (mock the HTTP sender):
  - `test_reenroll_success_writes_identity_and_verifies_heartbeat` → exit 0, state file updated, backup gone.
  - `test_reenroll_rejects_legacy_enrollment_token` → exit 2, state file untouched.
  - `test_reenroll_server_failure_restores_backup` → exit 2, original identity intact, backup file retained.
  - `test_reenroll_never_places_token_in_argv` (assert `sys.argv` contains only the flag, not the token; token only via file/env).
  - `test_reenroll_enters_loop_never` (no `run_forever`/loop call when flag set).
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** `run_reenroll` + argparse wiring (`--reenroll` store_true; mutually exclusive with the daemon loop).
- [ ] **Step 4: Run** — PASS.

### Task 2.2: `--apply-credential-file` flag

**Files:**
- Modify: `agent/nimbusops_agent/main.py`
- Test: extend `agent/tests/test_reenroll.py`

**Interfaces:**
- Produces: `run_apply_credential_file(state_path: Path, candidate_path: Path, server_url: str) -> int` — exit codes: `0` verified + identity replaced + candidate + backup removed; `1` network failure (everything kept); `3` server 401/403 (everything kept, candidate kept for retry); `2` precondition failure (missing identity, candidate == state path, malformed candidate JSON, missing token field).
- Behavior: candidate file is a 0600 JSON `{"agent_token": "..."}`; sends one heartbeat with the candidate token (including the configured `agent_mode` so verification does not clear a reported mode); replaces the identity only after a verified heartbeat; writes `agent.json.pre-apply-<utc>` backup first, deletes both files only on success.

- [ ] **Step 1: Failing tests**:
  - `test_apply_success_replaces_identity_and_cleans_up` → exit 0.
  - `test_apply_rejects_missing_identity` → exit 2.
  - `test_apply_rejects_candidate_equal_to_state_path` → exit 2.
  - `test_apply_unauthorized_keeps_everything` → exit 3, identity unchanged, candidate still present.
  - `test_apply_network_failure_keeps_everything` → exit 1.
  - `test_apply_no_token_in_argv_or_logs` (caplog assertion).
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run** — PASS.

### Task 2.3: Wrapper + docs

**Files:**
- Modify: `deploy/examples/bootstrap-enroll.sh.example` — add a `NIMBUSOPS_AGENT_ACTION=reenroll` branch: requires the state file to exist, passes `--reenroll`, exits with the agent's code; steady-state behavior unchanged. Validate with `sh -n`.
- Modify: `docs/OPERATOR_PROVISIONING.md` — document both one-shot flags, exit codes, and the prompt-to-file token entry.

- [ ] **Step 1**: implement + `sh -n deploy/examples/bootstrap-enroll.sh.example` — clean.
- [ ] **Step 2**: full gates (`pytest -q`, `npm test`, `tsc -b`, `vite build`).
- [ ] **Step 3**: `git commit -m "feat(agent): one-shot re-enroll and credential-file application"`.

---

## Slice 3 — Frontend: design primitives, code-aware errors, cookie-only auth

**Commit:** `feat(frontend): design primitives, code-aware errors, cookie-only auth`
**Owns tests:** `docker.host.test.tsx` rewrite, `client.guard.test.ts` additions, new primitive tests.

### Task 3.1: Design tokens + `ui/` primitives

**Files:**
- Modify: `frontend/tailwind.config.js` + `frontend/src/index.css` (tokens only, no new dependency)
- Create: `frontend/src/ui/Button.tsx`, `IconButton.tsx`, `Card.tsx`, `Panel.tsx`, `Field.tsx`, `Dialog.tsx`, `InlineAlert.tsx`, `CopyField.tsx`, `DescriptionList.tsx`, `Tabs.tsx`, `Skeleton.tsx`, `Toast.tsx`, `Kpi.tsx`
- Test: `frontend/src/ui/__tests__/primitives.test.tsx` (new)

**Interfaces:**
- Tokens: surfaces `ink-950/900/850/800`, `surface-0..3`, `border-subtle`, `border-strong`; signals `ok/warn/bad/info` + `revoked` (violet/slate) + `pending` (info-blue); type Inter 11/12/14/16/20/24/30, tabular numerals for metrics, mono for IDs/tokens/commands; radius 8/12/full; 1px borders; 4px spacing grid; focus = 2px `--focus` ring, 2px offset.
- `Dialog`: traps focus, closes on Escape, restores focus, labelled by its title; renders via portal.
- `Toast`: `aria-live="polite"`; `Button` keeps width when loading and sets `aria-busy`; every icon-only control requires an `aria-label` prop.

- [ ] **Step 1: Failing tests**: Button renders variants + disabled-with-reason; Dialog traps focus and restores on Escape; Toast announces politely; CopyField copies and announces.
- [ ] **Step 2: Run** — FAIL (module not found).
- [ ] **Step 3: Implement** primitives (compose from existing patterns in `components/`, no new deps).
- [ ] **Step 4: Run** — PASS.

### Task 3.2: `ApiFailure.code` + readiness + client additions

**Files:**
- Modify: `frontend/src/api/client.ts` (`ApiFailure`, `request()`, add `readiness()`, `listHostEvents()`, `listBootstrapTokens({active, limit})`)
- Modify: `frontend/src/api/types.ts` (`OnboardingState`, `HostEventOut`, new optional host fields, `ReadinessResponse`)
- Test: `frontend/src/api/client.guard.test.ts` (extend)

**Interfaces:**
- `ApiFailure` gains `code?: string`; `request()` parses `{"error":{"code","message"}}` into both.
- `readiness(): Promise<ReadinessResponse>` — uses raw `fetch` (NOT `request()`) and treats HTTP 503 as data (`ok:false, ready:false, database:"degraded"`); network failure → `ApiFailure("network", ...)`.
- `listHostEvents(hostId, limit?)` → `GET /hosts/{id}/events`.
- `listBootstrapTokens(opts?: {active?: boolean; limit?: number})` → `GET /operators/bootstrap-tokens?active=true&limit=N` (params only when set).

- [ ] **Step 1: Failing tests**: 503 body is returned as data (not thrown); error code is extracted; `listBootstrapTokens({active:true})` requests the right URL; `readiness()` network failure throws ApiFailure("network").
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run** — PASS.

### Task 3.3: Remove the legacy bearer path

**Files:**
- Modify: `frontend/src/api/client.ts` — delete `api.login`/`api.logout` (~lines 182-197), `operatorSessionToken`, `currentSessionToken`, `authHeaders` bearer injection; keep `browserLogin`/`browserLogout`/`me`
- Modify: `frontend/src/views/Servers.tsx` — delete the inline `EnrollFlow` component (lines 63-119) and its `api.login` call (line 80); keep `Servers` itself intact for now (full rewrite is slice 4)
- Modify: `frontend/src/api/types.ts` — drop `LoginResponse` if now unused
- Test: rewrite `frontend/src/views/__tests__/docker.host.test.tsx` (remove the `/operators/login` mock at line 22 and the bearer-header assertion at line 60; the view reads the cookie session like every other view), and update `enrollment.test.tsx`/`servers.test.tsx` references to the removed component

- [ ] **Step 1: Failing test**: `grep -r "api.login\|operatorSessionToken\|currentSessionToken" frontend/src` returns nothing (test via a tsc gate instead: `npx tsc -b` fails while the views still reference deleted exports — so update the views/tests in the same step).
- [ ] **Step 2: Run** full frontend gates — all green with the legacy path gone.
- [ ] **Step 3**: Confirm `Session.tsx` needs no change (it already uses cookie + CSRF via `browserLogin`).

### Task 3.4: `errorGuidance` + `StatePanels` rework

**Files:**
- Create: `frontend/src/lib/errorGuidance.ts`
- Modify: `frontend/src/components/StatePanels.tsx` (`ErrorPanel`/`InlineAlert` accept `ApiFailure` + guidance)
- Test: `frontend/src/lib/__tests__/errorGuidance.test.ts` (new)

**Interfaces:**
- `guidanceFor(failure: ApiFailure): {title: string; detail: string; action?: {label: string; to?: string; kind: "reenroll"|"refetch"|"fleet"|"reissue"}; surface: "browser"|"operation"|"agent"}`.
- Map (from spec §6): `HOST_REVOKED` → re-enroll; `HOST_NOT_FOUND` → fleet; `BOOTSTRAP_TOKEN_EXPIRED|CONSUMED|INVALID` → issue a new token; `BOOTSTRAP_TOKEN_ACTIVE` → revoke-and-reissue; `HOSTNAME_TAKEN` → re-enroll token; `OPERATOR_FORBIDDEN`/`OPERATOR_AUTH_REQUIRED` → sign-in note; `DOCKER_NOT_AUTHORIZED` → enable-Docker guidance; `AGENT_UNREACHABLE|TIMEOUT` → retry + re-enroll if persistent; network → check API. Unknown codes → generic title + the raw message + the code in mono.
- Never renders tokens, request bodies, or raw server internals.

- [ ] **Step 1: Failing tests**: every code in the table maps to the documented action; unknown code falls back; no secret in output for a message containing a token-shaped string.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.

### Task 3.5: Gates + commit

- [ ] Full pytest + npm test + tsc + build green.
- [ ] `git commit -m "feat(frontend): design primitives, code-aware errors, cookie-only auth"`.

---

## Slice 4 — Frontend: zero-friction enrollment wizard

**Commit:** `feat(frontend): zero-friction enrollment wizard`
**Owns tests:** `enrollment.test.tsx` rewrite, `servers.test.tsx` rewrite, new wizard tests.

### Task 4.1: `lib/onboarding.ts` + `lib/agentCommands.ts` + `hooks/useOnboarding.ts`

**Files:**
- Create: `frontend/src/lib/onboarding.ts`, `frontend/src/lib/agentCommands.ts`, `frontend/src/hooks/useOnboarding.ts`
- Test: `frontend/src/lib/__tests__/onboarding.test.ts`

**Interfaces:**
- `deriveOnboardingState(tokens: BootstrapTokenOut[], hosts: Host[], hostname: string, now: number): OnboardingState` — WAITING (no consumed_at/revoked_at, expires_at > now), EXPIRED (same but past), CONSUMED (consumed_at != null), REVOKED (revoked_at != null and not consumed); matches the host by hostname (normalized, case-insensitive).
- `installCommands(origin: string, stateDir: string): {promptToFile: string; systemdTab: string[]; foregroundTab: string}` — the prompt-to-file snippet (`umask 077; read -rsp "Bootstrap token: " t; echo; printf "%s" "$t" > <stateDir>/bootstrap.token; unset t`), the environment contract lines (`NIMBUSOPS_INSTALL_DIR`, `NIMBUSOPS_SERVER_URL`, `NIMBUSOPS_TOKEN_FILE`, `NIMBUSOPS_STATE_FILE`, `NIMBUSOPS_AGENT_MODE`), and the foreground command `python -m nimbusops_agent --bootstrap-token-file <stateDir>/bootstrap.token`. **No token parameter anywhere.**
- `useOnboarding()` — single poll (3 s while `document.visibilityState === "visible"`, paused otherwise; in-flight guard); reads `listBootstrapTokens({active:true, limit:50})` + `listHosts()`; exposes `{state, token, host, reissue(), cancel()}`.

- [ ] **Step 1: Failing tests** for the pure functions (state derivation matrix, command templates contain no token and no `--token`, host-exists detection).
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.

### Task 4.2: `views/Onboarding.tsx` wizard (5 steps) + route

**Files:**
- Create: `frontend/src/views/Onboarding.tsx`
- Modify: `frontend/src/App.tsx` — declare `/servers/new` **before** `/servers/:hostId`; ADMIN-gate the route (VIEWERs never reach it)
- Test: `frontend/src/views/__tests__/onboarding.test.tsx` (new)

**Interfaces:**
- Steps: (1) Host — hostname trimmed 1-255; on submit, an exact fleet match routes to "This host already exists" with `Re-enroll` / `Open host` links. (2) Mode — telemetry-only vs executor copy; notes `docker_enabled` is a separate default-off permission. (3) Token — real `api.issueBootstrapToken(hostname, ttl)` with `intent="enroll"`; token shown once, expiry countdown, copy button, "cannot be shown again"; `Reissue` revokes the previous token first and maps `BOOTSTRAP_TOKEN_ACTIVE` to revoke-and-retry. (4) Install — `installCommands(window.location.origin, "/var/lib/nimbusops-agent")`; tabs systemd/foreground. (5) Verify — checklist polling token consumed → host exists → first heartbeat → first telemetry; `Continue to host` enabled only when the host exists; expiry switches to EXPIRED with one `Issue a new token` action.
- No optimistic success: the flow advances only on confirmed backend responses.

- [ ] **Step 1: Failing tests**:
  - `test_wizard_issues_real_token_on_step3` (fetch mock asserts a POST to `/operators/bootstrap-tokens` with `{hostname, intent:"enroll"}` happened before any token is displayed).
  - `test_commands_contain_no_token` (render install step; assert the token string never appears in the DOM).
  - `test_waiting_persists_until_consumed_and_host` (mock consumed token + no host → step 5 shows "waiting" copy, Continue disabled).
  - `test_expiry_offers_reissue` (expired token → EXPIRED panel with one action).
  - `test_bootstrap_token_active_offers_revoke_and_reissue` (issue → 409 with the code; the retry path revokes then reissues).
  - `test_duplicate_hostname_routes_to_reenroll` (existing fleet match at step 1).
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.

### Task 4.3: `Servers.tsx` rewrite (fleet + filters + onboarding rows)

**Files:**
- Modify: `frontend/src/views/Servers.tsx` (full rewrite; delete the rest of the old `EnrollFlow` surface)
- Modify: `frontend/src/hooks/useFleet.ts` if not already created in 4.1 (single fleet polling source; in-flight guard; pause when hidden)
- Test: rewrite `frontend/src/views/__tests__/servers.test.tsx`, update `enrollment.test.tsx`

**Interfaces:**
- Header: title, count, `Add server` (ADMIN → `/servers/new`), refresh. Filter chips `ALL|ONLINE|STALE|OFFLINE|REVOKED|AWAITING`; search box filters by hostname substring.
- Rows: real hosts with honest metrics (`—` for missing); revoked hosts render the REVOKED badge + a `Re-enroll` link to the wizard's re-enroll entry (no other action); an "Awaiting enrollment" row per active token (derived via `deriveOnboardingState`), clearly labeled as not-yet-a-host.
- The unregister dialog (ADMIN, typed hostname confirmation, revoke-to-tombstone semantics) is preserved; its fixtures stay.

- [ ] **Step 1: Failing tests**: filter chips filter; awaiting row appears for an active token; revoked row shows REVOKED + re-enroll; search filters; API failure shows the error panel with retry, not a blank page.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** full gates — PASS.
- [ ] **Step 5**: `git commit -m "feat(frontend): zero-friction enrollment wizard"`.

---

## Slice 5 — Frontend: host lifecycle, history, and service panels

**Commit:** `feat(frontend): host lifecycle, history, and service panels`
**Owns tests:** lifecycle dialog tests, events history tests, runtime-panel tests.

### Task 5.1: Extract `HostActions` + `CredentialDialogs` + `ConfirmDialog`

**Files:**
- Create: `frontend/src/views/host/HostActions.tsx`, `frontend/src/views/host/CredentialDialogs.tsx`, `frontend/src/ui/ConfirmDialog.tsx` (or under `views/host/`)
- Test: `frontend/src/views/__tests__/lifecycle.test.tsx` (new)

**Interfaces:**
- `ConfirmDialog`: generic typed-confirmation dialog (`confirmLabel`, `expectedValue` for type-to-confirm, consequences list).
- `CredentialDialogs`: `RotateCredentialDialog` (calls `api.rotateCredential(hostId)`; shows the new token ONCE in a transient panel with copy + "clears when closed"; grace countdown from `credential_grace_until`; hard warning that the host must be updated before grace ends, else re-enroll) and `ReenrollDialog` (calls `api.reenrollHost(hostId)` → shows the bootstrap token once + expiry countdown; on `BOOTSTRAP_TOKEN_ACTIVE` refetches the token list, matches the hostname, offers revoke-and-retry; polls `credential_version` + `is_revoked=false` + `last_seen_at` to confirm — **never** the `RE_ENROLLED` event string).
- `HostActions`: ADMIN-only render gate (`useAdmin()`); revoke (typed hostname, calls `api.revokeHost`), rotate, re-enroll buttons; VIEWER renders nothing.

- [ ] **Step 1: Failing tests**: revoke requires typing the hostname and calls the exact endpoint; rotate shows the token once and clears the DOM on close (`queryByText(token)` after close); re-enroll polls `credential_version`, not `RE_ENROLLED`; VIEWER sees no buttons; `BOOTSTRAP_TOKEN_ACTIVE` path revokes the stale token and retries.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.

### Task 5.2: `HostDetail` runtime panel + events history

**Files:**
- Modify: `frontend/src/views/HostDetail.tsx`
- Test: extend `views.test.tsx`

**Interfaces:**
- Runtime panel rows: reported mode (`agent_mode`, "not reported" when null — never guessed from `docker_enabled` alone), Docker permission, credential version, grace deadline (only when non-null), last heartbeat/telemetry, and the exact next action (re-enroll for revoked).
- The "Agent status" row (lines 104-113) gains a revoked branch: "Credential revoked — re-enroll required" (today it falls through to "Not reporting").
- Events section: newest-first list from `listHostEvents` with actor + event + timestamp; empty state "No events yet"; error state non-blocking.

- [ ] **Step 1: Failing tests**: revoked host shows "Credential revoked — re-enroll required"; `agent_mode=null` renders "not reported"; grace countdown renders only when `credential_grace_until` is non-null; events render newest-first with the mocked API.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.

### Task 5.3: `ServerDetail` simplification

**Files:**
- Modify: `frontend/src/views/ServerDetail.tsx` — real hosts only; delete sim branches (`listSimServers`, `isSimulatedHostId` imports go)
- Test: update `console.test.tsx` simulated-navigation cases to real-host fixtures (this is the slice-6-adjacent cleanup, done here only for the branches this slice's edits touch; full sim removal stays slice 7)

- [ ] **Step 1**: run gates after the edit; fix what the removal breaks.
- [ ] **Step 2**: `git commit -m "feat(frontend): host lifecycle, history, and service panels"`.

---

## Slice 6 — Frontend: unified dashboard, settings, and status consumers

**Commit:** `feat(frontend): unified dashboard, settings, and status consumers`
**Owns tests:** dashboard tests, Settings tests, `applications.test.tsx` additions, `console.test.tsx` updates.

### Task 6.1: `views/Overview.tsx` → dashboard

**Files:**
- Modify: `frontend/src/views/Overview.tsx`
- Test: extend `views.test.tsx`

**Interfaces:**
- Sections: (1) KPI cards — total hosts, ONLINE/STALE/OFFLINE/REVOKED counts (extend the existing `Overview.tsx:50-52` count logic), awaiting-enrollment count; (2) "Needs attention" — real rows only: revoked, stale/offline, tokens expiring < 5 min or expired, `docker_enabled=true` with `telemetry-only`/null mode, degraded control plane (from `/health`); each entry links to its one resolving action; (3) compact fleet table sorted by attention; (4) last 5 real operations (`api.listOperations({limit:5})`) with status + error code → Activity link.
- No synthetic counters; no "all systems operational" claim unless `/health` is ok AND nothing needs attention.

- [ ] **Step 1: Failing tests**: revoked host appears in Needs attention (not in ONLINE count); attention entry links to the right action; operations section renders real operations; "operational" banner absent when something needs attention.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.

### Task 6.2: `views/Settings.tsx` (account + control plane + deployment reference)

**Files:**
- Create: `frontend/src/views/Settings.tsx`
- Modify: `frontend/src/App.tsx` (route)
- Test: `frontend/src/views/__tests__/settings.test.tsx` (new)

**Interfaces:**
- Account: username/role from `useSession`, sign out (`api.browserLogout`).
- Control plane: `api.health()` + `api.readiness()` (503-as-data), version/build, database state, latency, last check, manual recheck button; degraded → concrete checks (process, DB path, logs), **no restart button**.
- Deployment reference: copyable unit paths + the environment contract; "not installed by NimbusOps" note; plain text only, no dead app routes to `deploy/examples/`.

- [ ] **Step 1: Failing tests**: readiness 503 renders "degraded" state with recovery steps (not an error); recheck refetches; account section renders the session user; sign out calls the logout endpoint.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.

### Task 6.3: Status-consumer corrections

**Files:**
- Modify: `frontend/src/views/Applications.tsx` (lines 289-302): VIEWER → hide deploy/start/stop (today disabled); REVOKED copy → "re-enroll required" instead of "will run when the agent reconnects"
- Modify: `frontend/src/components/ServerList.tsx` + `frontend/src/views/Activity.tsx` — remove `simRegistry` imports (their sections collapse to real hosts; full sim deletion is slice 7)
- Modify: `frontend/src/App.tsx` — `/hosts/:hostId` redirects to `/servers/:hostId`
- Test: `applications.test.tsx` gains a VIEWER case and a REVOKED case (today it mocks only `useAdmin:true` and has neither)

- [ ] **Step 1: Failing tests**: VIEWER has no deploy control in the DOM; revoked host shows "re-enroll required" copy; `/hosts/x` redirects to `/servers/x`.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.
- [ ] **Step 5**: `git commit -m "feat(frontend): unified dashboard, settings, and status consumers"`.

---

## Slice 7 — Frontend: remove simulation registry, E2E harness, acceptance doc

**Commit:** `feat(frontend): remove simulated registry and finalize verification`

### Task 7.1: Delete `simRegistry` and all remaining consumers

**Files:**
- Delete: `frontend/src/lib/simRegistry.ts` + `frontend/src/lib/simRegistry.test.ts`
- Modify: `frontend/src/views/Servers.tsx`, `ServerDetail.tsx`, `Activity.tsx`, `components/ServerList.tsx` (any leftover imports), `views/__tests__/auth.test.tsx`, `console.test.tsx` (rewrite simulated sections to real-host fixtures)
- Keep: the server-side `SIMULATED_HOST_REJECTED` guard and the client `assertNotSimulated` mutation guard (`client.guard.test.ts` stays green) as defense in depth.

- [ ] **Step 1: Grep gate**: `grep -r "simRegistry\|addSimServer\|listSimServers\|SIMULATED-" frontend/src` → only `client.ts`/`client.guard.test.ts` `sim-` guard matches remain.
- [ ] **Step 2**: delete + rewrite the tests; full `npm test` green; `npx tsc -b`; `npx vite build`.

### Task 7.2: Optional E2E harness (committed, not a CI gate)

**Files:**
- Create: `frontend/scripts/e2e-onboarding.mjs` (Playwright; starts a temp-DB API + Vite; drives ADMIN and VIEWER contexts; asserts revoked ≠ offline, wizard issues a real token, VIEWER has no actions, dialogs keyboard-operable)
- Modify: `frontend/package.json` (script only, devDependency only if Playwright is approved — otherwise the script documents the requirement)
- Modify: `docs/E2E.md` or `docs/DEVELOPMENT.md` — "optional local gate; not in CI until approved"

- [ ] **Step 1**: write the harness; do NOT add a CI job (that is a separate infrastructure decision).
- [ ] **Step 2**: document honestly: "requires `npx playwright install chromium`; not a CI gate".

### Task 7.3: Sprint acceptance doc + data-compat check

**Files:**
- Create: `docs/SPRINT1_UX_ACCEPTANCE.md` — what shipped, evidence (test counts, grep outputs), what remains unverified (real systemd install, Docker acceptance, soak).
- Data-compat check: copy the demo DB, run startup migration on the copy, verify operators/hosts/telemetry/operation counts unchanged and host identities stable (read-only; the live DB is never touched).

- [ ] **Step 1**: run the compat check; record output in the acceptance doc.
- [ ] **Step 2**: full four-gate run.
- [ ] **Step 3**: `git commit -m "feat(frontend): remove simulated registry and finalize verification"`.

---

## Self-review notes

- **Spec coverage**: D1 (Task 1.1/1.3), D2 (1.4/4.1/4.2), D3 (1.2/1.3/5.2), D4 (6.2/5.2), D5 (4.3/6.3), D6 (2.1/2.2/5.1), errors (3.2/3.4), design system (3.1), a11y (3.1/4.2/5.1), verification plan (1.9/2.3/5.3/6.3/7.3), E2E (7.2), risks → Review Focus. No spec section lacks a task.
- **Step scan**: each step is one implementable action; signatures and exact values are pinned; no TBD lines.
- **Type consistency**: `OnboardingState` defined in 3.2 (types.ts), consumed in 4.1/4.3; `deriveOnboardingState` defined in 4.1, consumed in 4.3; `effective_status` defined in 1.1, consumed by `HostOut` population in 1.3; exit codes consistent between 2.1/2.2 and the wrapper in 2.3.
- **Review Focus** lines each have an owning test named in their slice.
- **Proportion**: plan is ~450 lines vs the 822-line spec — compressed to signatures + assertions, no transcript bodies.





