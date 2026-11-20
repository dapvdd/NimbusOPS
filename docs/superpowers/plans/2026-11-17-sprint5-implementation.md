# Sprint 5 Zero-Touch Provisioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver authorized zero-touch agent provisioning (discover → validate → approve → durable job → managed install → verified enrollment) on LOCAL_WINDOWS, GENERIC_LINUX and existing AZURE_VM targets, with honest states and no false success.

**Architecture:** DB-backed provisioning engine (SQLAlchemy/SQLite WAL) plus a separate worker process; provider adapters behind a fixed typed interface; managed enrollment with target-generated candidate credentials and job-bound challenge/receipt verification; machine-level ownership with admission-closed dispatch fencing.

**Tech Stack:** FastAPI + SQLAlchemy (existing), pytest, React/Vite (existing), OpenSSH subprocess transport (Linux manager), named pipes + WinSW (Windows), azure-identity/azure-mgmt-compute (Azure, pinned).

**Spec:** `docs/superpowers/specs/2026-11-17-sprint5-full-design.md` (§15 normative, §16 ADR index, ADRs in `docs/superpowers/specs/adr/`). This plan is documentation; it is NOT authorization to execute.

**Status: PLAN AWAITING SEPARATE IMPLEMENTATION APPROVAL.**

## Global Constraints

- Baseline `f3a8809`; branch `sprint/zero-touch-provisioning`; additive-only; existing auth/telemetry/Docker/host contracts preserved.
- Seven job states only; terminal immutable; retry = new linked child job.
- Persist dispatch intent before any network call; adapter outcomes exactly NOT_SUBMITTED | ACCEPTED | COMPLETED | UNKNOWN; timeout after send is UNKNOWN.
- CLOSED attempts never reopen; no automatic duplicate external execution after uncertainty; ownership keyed by machine_id, survives lease loss.
- `hosts.revocation_revision` increments on every revoke; authority predicates carry expected revisions; revoke/cancel close OPEN attempts.
- No secrets in logs, URLs, browser storage, argv, provider scripts or durable diagnostics; error surfaces are typed codes + remediation only.
- Success requires: supervisor-confirmed runtime + CURRENT-credential challenge heartbeat + fresh telemetry receipts (§7); helper/one-shot success never qualifies.
- SQLite WAL local disk only; short `BEGIN IMMEDIATE` transactions; no transaction across network I/O; `synchronous=FULL` verified.
- Timeouts/defaults from design §5 (lease 30s/10s renewal; 3 attempts; backoff 5s→60s full jitter; grant TTL 5min; job deadline 20min).
- Approval continuation rules per §15.5; Azure binding refreshed before every mutating authorization per §15.6.
- Every task: failing test first (RED), minimal implementation (GREEN), full targeted regression, scoped commit, independent review.

## Review Focus

1. **Old ONLINE badge after provisioning failure** — a host that looks ONLINE (stale heartbeat) must never satisfy job success; expect verification to require job-bound receipts. Pinned by D4 test `test_success_requires_job_bound_receipts`.
2. **Duplicate install after worker crash at dispatch boundary** — a crashed worker whose SDK call may have landed must never be auto-retried; expect reconciliation or blocked state. Pinned by D3 `test_crash_after_acceptance_blocks_redispatch`.
3. **Old credential resurrection** — after failed rotation, re-enroll or rollback, the previous revoked/grace credential must stay unusable. Pinned by D5 `test_no_old_credential_restoration`.
4. **Manager replay/closed-dispatch acceptance** — a delayed worker whose attempt was CLOSED must be refused by the manager even with valid-looking bindings. Pinned by D6L/D6W `test_closed_dispatch_refused`.
5. **Azure binding staleness** — a grant exchange or manager call for a recreated VM (same ARM ID, new vmId) must fail closed. Pinned by D7 `test_stale_vm_binding_denied`.

---

## Part 1 — Contracts and durable core (D0–D2)

### Task D0.1: Freeze OpenAPI and wire fixtures

**Files:**
- Modify: `docs/superpowers/specs/2026-11-17-sprint5-openapi.json` (fixes only)
- Create: `backend/tests/provisioning/fixtures/manager_wire_v1.json` (golden request/receipt fixtures for STATUS/ADMIT/START_ACTION/CONFIRM_ACTIVATION/ARM_CHALLENGE/CANCEL/CLOSE_RESULT)
- Test: `backend/tests/provisioning/test_contract_structure.py`

**Interfaces:**
- Produces: validated OpenAPI file; `load_wire_fixture(name) -> dict` fixture loader used by D2/D3/D4/D6/D7 tests.
- Consumes: design §15.4 message table (fields pinned there).

- [ ] **Step 1: Write failing structure test** — asserts every OpenAPI path resolves, every manager fixture has `protocol_version=1`, `job_id`, `dispatch_id`, `intent_hash`, `machine_binding`, `ownership_generation`, `expected_credential_version`, `expected_revocation_revision`, `request_id`, `journal_sequence`.
- [ ] **Step 2: Run** `pytest backend/tests/provisioning/test_contract_structure.py -v` — expect FAIL (fixtures absent).
- [ ] **Step 3: Create fixtures** exactly per §15.4; no secret fields anywhere in fixtures.
- [ ] **Step 4: Run Redocly if available** (`npx --yes @redocly/cli lint docs/superpowers/specs/2026-11-17-sprint5-openapi.json`); if network-blocked, record skip in evidence file — structural validator stays the floor.
- [ ] **Step 5: Commit** `docs(provisioning): freeze wire fixtures and contract`.

### Task D1.1: Additive schema and migration

**Files:**
- Modify: `backend/app/models/__init__.py` (append provisioning models)
- Modify: `backend/app/core/migrations.py` (new `_S5_TABLES` set + marker `sprint5_migration_marker`)
- Test: `backend/tests/provisioning/test_schema_migration.py`

**Interfaces:**
- Produces: ORM models `ProvisioningMachine`, `ProvisioningConnection`, `ProvisioningTarget`, `ProvisioningValidation`, `ProvisioningJob`, `ProvisioningRequest`, `ProvisioningOwnership`, `ProvisioningAttempt`, `ProvisioningEvent`, `ProvisioningGrant`, `ProvisioningCredentialCommit`, `ProvisioningChallenge`, `ProvisioningReceipt` with columns exactly per design §4 (plus §15 additions: `admission_state/closed_at/closure_reason` on attempts; `machine_id` on targets; `expected_revocation_revision` on validations/grants/commits; `revocation_revision` on hosts).
- Produces: `migrations.run_sprint5_migrations(engine) -> None` idempotent; `assert_provisioning_readiness(engine) -> ReadinessReport`.
- Consumes: baseline `utcnow/new_uuid`, existing migration conventions.

- [ ] **Step 1: Failing migration test** — run migrations on a copy of a populated f3a8809 DB fixture: all new tables exist; `hosts` gains `revocation_revision INTEGER NOT NULL DEFAULT 0`; existing rows (hosts, tokens, ops) byte-identical except new column default; re-run is a no-op; FK `provisioning_targets.host_id` RESTRICT.
- [ ] **Step 2: Run** — expect FAIL (models absent).
- [ ] **Step 3: Implement models + migration** (additive CREATE TABLE IF NOT EXISTS + ALTER TABLE hosts ADD COLUMN with pragma check; readiness checks unique indexes and fails closed with typed report, never deletes collisions).
- [ ] **Step 4: Run** — expect PASS; also run full `pytest backend/tests -q` to prove no regression.
- [ ] **Step 5: Commit** `feat(provisioning): additive schema and readiness migration`.

### Task D2.1: Provisioning service core — validation and job submission

**Files:**
- Create: `backend/app/services/provisioning/__init__.py`, `backend/app/services/provisioning/validations.py`, `backend/app/services/provisioning/jobs.py`
- Modify: `backend/app/api/` (new `provisioning.py` router registered additively)
- Test: `backend/tests/provisioning/test_validation_service.py`, `test_job_submission.py`

**Interfaces:**
- Consumes: D1 models; baseline `check_csrf/resolve_request` pattern (`operators.py:42-66`); `EnrollRequest` hostname normalization rules (§2).
- Produces: `create_validation(db, actor, req) -> Validation` (immutable plan_json/plan_hash, expires 10min, read-only checks); `consume_validation_for_job(db, actor, approval, idempotency_key, request_hash) -> Job` (atomic: fingerprint match, scope, ownership acquire by machine_id, request row, PENDING job, CREATED event, one commit); replay same key/body → same job; mismatch → 409 TARGET_BUSY/IDEMPOTENCY_CONFLICT; `normalize_hostname(raw) -> str` raising typed errors.

- [ ] **Step 1: Failing tests** — validation immutability/expiry (410 after 10min); idempotent replay returns same job id; same key different fingerprint → 409; hostname normalization cases (` sim `, `Sim-1`, trailing dot, 254 chars → typed 422); VIEWER 403 on both endpoints; CSRF/origin enforced on POSTs; 404 conceals out-of-scope target.
- [ ] **Step 2: Run** — FAIL (modules absent).
- [ ] **Step 3: Implement** services + router; no state transition engine yet (jobs stay PENDING).
- [ ] **Step 4: Run** targeted + `pytest backend/tests -q`.
- [ ] **Step 5: Commit** `feat(provisioning): validation review and idempotent job submission`.

### Task D2.2: Ownership guard and lifecycle conflict rules

**Files:**
- Modify: `backend/app/services/provisioning/ownership.py` (create), `backend/app/services/hosts.py` (revoke/re-enroll consult guard), `backend/app/services/deployments.py` (Docker dispatch consults guard)
- Test: `backend/tests/provisioning/test_ownership_guards.py`

**Interfaces:**
- Consumes: D1 `ProvisioningOwnership`; baseline `enroll_host`, revoke paths, `DeploymentOperation` claim logic (`deployments.py:43-83`).
- Produces: `acquire_machine_ownership(db, machine_id, job_id) -> generation` (FAIL if HELD/RECONCILING); `assert_lifecycle_allowed(db, host_id) -> None` raising 409 when an identity-changing job holds the machine; `release_after_resolution(...)`; revoke always allowed + closes OPEN attempts + bumps `revocation_revision` (§15.2); Docker mutations during identity jobs → 409 + quarantine pending ops (no change to Docker authorization semantics).

- [ ] **Step 1: Failing tests** — second job on same machine_id denied; revoke during active job closes OPEN attempt + bumps revision + verifier cannot succeed after; concurrent manual rotate during held ownership → 409; Docker enable during identity job → 409 with quarantined ops; monitoring reads unaffected.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** guard functions + minimal hooks in existing services (additive; no behavior change when no provisioning rows exist).
- [ ] **Step 4: Run** targeted + full backend suite.
- [ ] **Step 5: Commit** `feat(provisioning): machine ownership and lifecycle guards`.

## Part 2 — Worker, dispatch and enrollment (D3–D4)

### Task D3.1: Worker loop, leases, claims

**Files:**
- Create: `backend/app/provisioning_worker/__init__.py`, `main.py` (entrypoint `python -m app.provisioning_worker`), `leases.py`, `engine.py`
- Test: `backend/tests/provisioning/test_worker_leases.py`

**Interfaces:**
- Consumes: D1/D2 (jobs, ownership); design §5 lease defaults (30s/10s, generation CAS).
- Produces: `claim_due_jobs(db, owner_id, now) -> list[Job]` (atomic lease CAS, generation++, due = lease expired AND next_check_at passed AND not dispatch_blocked); `renew_lease(db, job_id, owner_id, generation) -> bool`; `record_event(db, job, code, detail)` allocating sequence from job revision in same transaction; `evaluate_transitions(db, job, now) -> None` implementing the §3 transition table + terminal immutability + deadline/reconciliation semantics (UNKNOWN effects never auto-FAILED).

- [ ] **Step 1: Failing tests** — two concurrent claimers never both own (transactional CAS); expired lease steal increments generation; stale-generation write refused; PENDING→VALIDATING→RUNNING happy path; terminal states immutable; deadline with UNKNOWN effect stays nonterminal with `reconciliation_required=true`; event sequence gap-free.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** leases/engine (BEGIN IMMEDIATE, jittered retry ×3, busy→503 semantics in API only; worker logs and backs off).
- [ ] **Step 4: Run** targeted + backend suite.
- [ ] **Step 5: Commit** `feat(provisioning): worker leases and durable transitions`.

### Task D3.2: Dispatch intents, four-valued outcomes, reconciliation

**Files:**
- Create: `backend/app/services/provisioning/dispatch.py`, `backend/app/services/provisioning/adapters/base.py`
- Modify: `backend/app/provisioning_worker/engine.py`
- Test: `backend/tests/provisioning/test_dispatch_fencing.py`

**Interfaces:**
- Consumes: D3.1; `provisioning_attempts` columns; §5 protocol.
- Produces: `submit_with_intent(db, job, attempt, adapter_call)` — persists INTENT (dispatch_id, intent_hash, correlation) → calls adapter → persists outcome; typed outcomes `NOT_SUBMITTED | ACCEPTED(handle) | COMPLETED(receipt) | UNKNOWN`; `close_open_attempt(db, attempt_id, reason)` CAS on admission_state; `reconcile(db, job)` — successor uses persisted correlation + manager STATUS, never re-dispatches on UNKNOWN; `admit(db, attempt) -> receipt` CAS checking revocation_revision + cancel + lease + generation (§15.1).

- [ ] **Step 1: Failing tests** (fake adapter with scripted outcomes) — crash before intent commit → no adapter call; crash after adapter call before outcome commit → next worker UNKNOWN-blocks (call count stays 1); definitive provider rejection → NOT_SUBMITTED + retry allowed; timeout-after-send → UNKNOWN + `dispatch_blocked` + no retry; CLOSED attempt rejected by manager fixture; cancel/revocation closes OPEN attempt.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** dispatch + base adapter + engine wiring.
- [ ] **Step 4: Run** targeted + suite.
- [ ] **Step 5: Commit** `feat(provisioning): durable dispatch, admission fencing, reconciliation`.

### Task D3.3: Retry, backoff, cancellation

**Files:**
- Modify: `engine.py`, `dispatch.py`, new `backend/app/services/provisioning/policy.py`
- Modify: API router (cancellation/retries endpoints per contract)
- Test: `backend/tests/provisioning/test_retry_cancel.py`

**Interfaces:**
- Consumes: D3.1/D3.2; §5 defaults (3 attempts, 5s→60s full jitter, deadlines); §15.5 continuation.
- Produces: `next_backoff(attempt_no, rng) -> seconds`; `request_cancellation(db, job_id, actor)` — idempotent intent, 202 until settled, terminal→409; `create_child_retry(db, parent_id, actor, approval)` — only FAILED/CANCELLED + resolved ownership + fresh validation; approval-expiry admission rules (§15.5).

- [ ] **Step 1: Failing tests** — fake-clock backoff schedule; 4th attempt refused; cancel before dispatch → CANCELLED cleanly; cancel during ADMITTED → stops at safe boundary, reconciled, then CANCELLED; cancel after SUCCEEDED → 409; retry links child, inherits target, requires fresh validation; expired approval blocks new ADMIT but continues journaled steps (fixture).
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** targeted + suite.
- [ ] **Step 5: Commit** `feat(provisioning): bounded retries, cancellation, child retries`.

### Task D4.1: Managed enrollment commit protocol

**Files:**
- Create: `backend/app/services/provisioning/grants.py`, `backend/app/services/provisioning/enroll_commit.py`
- Modify: `backend/app/api/agents.py` (add grant-exchange + managed-enrollments routes; legacy routes untouched)
- Modify: `backend/app/services/hosts.py` (add `AuthContext`-returning internal wrapper; keep public behavior)
- Test: `backend/tests/provisioning/test_managed_enrollment.py`

**Interfaces:**
- Consumes: baseline `generate_agent_token/hash_token`, `consume_bootstrap_token` transaction shape; D2 ownership; §7 protocol; §15.2 revisions.
- Produces: `issue_grant(db, job, dispatch, binding) -> Grant`; `commit_managed_enrollment(db, grant_token, req) -> CredentialCommit` — one transaction: validate grant/dispatch/mapping/revisions/ownership, consume grant, create-or-rotate same host_id, clear grace, bump credential_version, write commit record + event; duplicate same grant+candidate → original metadata; different candidate → 409; `commit_status(db, host_id, commit_id) -> current: bool` for current-credential auth only.

- [ ] **Step 1: Failing tests** — atomic commit creates host with correct version; response contains no secret; replay returns same metadata (not an un-revoke); wrong candidate → 409; revoke-before-commit → 401 + grant invalidated; revoke-after-commit → status 401 for new credential; grant TTL expiry; hostname mismatch; INSTALL on already-enrolled hostname → fail closed.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** services + routes (bodies/headers excluded from logging).
- [ ] **Step 4: Run** targeted + backend suite + existing enrollment tests untouched.
- [ ] **Step 5: Commit** `feat(provisioning): managed enrollment commit with safe replay`.

### Task D4.2: Challenge/receipt verification

**Files:**
- Create: `backend/app/services/provisioning/verification.py`
- Modify: `backend/app/api/agents.py` heartbeat/telemetry (optional `provisioning_proof`), `backend/app/services/hosts.py` (receipt writes in same transaction)
- Test: `backend/tests/provisioning/test_verification.py`

**Interfaces:**
- Consumes: D4.1; §7 predicate; `AuthContext(host_id, credential_version, matched_slot, is_revoked)`.
- Produces: `arm_challenge(db, job, host, runtime_instance_id) -> nonce`; `record_receipt(db, auth_ctx, kind, proof, ...)`; `evaluate_success(db, job) -> (ok, reason)` implementing ALL five §7 conditions (CURRENT slot only, unconsumed challenge, activation sequence < receipt sequence, telemetry freshness/skew/bounds, artifact/config match, host not revoked at CAS).

- [ ] **Step 1: Failing tests** — success path passes all five; GRACE-slot heartbeat rejected; stale telemetry rejected; replayed challenge rejected; wrong runtime/host rejected; old ONLINE without receipts rejected; revoked host fails at CAS; re-armed challenge after stale receipt works for same live runtime (§15.4).
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** targeted + suite.
- [ ] **Step 5: Commit** `feat(provisioning): job-bound challenge and receipt verification`.

## Part 3 — OS installers and manager (D5–D6)

### Task D5.1: Agent pending journal and credential handoff

**Files:**
- Modify: `agent/nimbusops_agent/config.py` (fail-closed ACL helper, journal read/write)
- Create: `agent/nimbusops_agent/journal.py`
- Modify: `agent/nimbusops_agent/main.py` (startup: pending-journal recovery before old runtime start)
- Test: `agent/tests/provisioning/test_journal.py`, `test_handoff.py`

**Interfaces:**
- Consumes: baseline `save_identity` atomic replace; §7 steps 6–7.
- Produces: `write_pending_candidate(state_dir, candidate_id, job_id, dispatch_id, credential) -> None` (protected dir, ACL verified fatal, fsync file+dir / Windows write-through); `read_pending_candidate(state_dir) -> Candidate | None`; `promote_candidate(...) -> None` (atomic replace, no old-credential restore after commit); startup hook: pending PREPARED journal → verify current commit via status route → promote or stop safely (never boot old identity after commit).

- [ ] **Step 1: Failing tests** — ACL failure on Windows aborts before secret write (not swallowed); candidate never equals active identity path; promotion after confirmed commit keeps host_id; simulated "commit done + crash before promote" → startup recovers candidate, never old token; old token after commit → daemon does not start with it.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** agent suite (POSIX mode test still skipped on Windows).
- [ ] **Step 5: Commit** `feat(agent): protected pending journal and safe credential handoff`.

### Task D5.2: Daemon restart with fresh Sender + proof loop

**Files:**
- Modify: `agent/nimbusops_agent/main.py` (run loop reads challenge state each heartbeat; constructs Sender at process start only)
- Modify: `agent/nimbusops_agent/client.py` (send `provisioning_proof` when challenge state present; telemetry sample_sequence)
- Test: `agent/tests/provisioning/test_proof_loop.py`

**Interfaces:**
- Consumes: D4.2 schemas; `host_info_snapshot` mode reporting consistency.
- Produces: `read_challenge_state(state_dir) -> ChallengeState | None`; heartbeat includes `provisioning_proof` only when armed & unexpired; sample_sequence increments per send; helper paths never read challenge state.

- [ ] **Step 1: Failing tests** — daemon restart loads new identity and proves fresh runtime (loopback fake server records runtime_instance_id); challenge expiry → proof omitted, not stale replayed; one-shot helper never sends proof; normal heartbeat without provisioning job unchanged (legacy contract).
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** agent suite + integration suite.
- [ ] **Step 5: Commit** `feat(agent): runtime proof reporting with fresh Sender lifecycle`.

### Task D6L.1: Linux manager + systemd packaging

**Files:**
- Create: `agent/manager/linux/nimbusops_manager.py` (root-owned fixed binary entry), `agent/manager/linux/install.sh`, systemd units under `deploy/`
- Test: `backend/tests/provisioning/test_linux_manager_protocol.py` (framing/journal via fake SSH)
- Real-host gate: G7 (documented, not executed now)

**Interfaces:**
- Consumes: ADR-5.3 (SSH, sudoers, stdin JSON); §15.4 messages; §8 Linux layout.
- Produces: manager script implementing STATUS/ADMIT/START_ACTION/CONFIRM_ACTIVATION/ARM_CHALLENGE/CANCEL/CLOSE_RESULT with journal at `/var/lib/nimbusops-agent/manager/journal.jsonl` + OS lock; installer staging releases by digest; unit template parameters (user, paths) fixed in ADR-5.5 layout.

- [ ] **Step 1: Failing protocol tests** (subprocess-driven with fake SSH harness on Windows dev) — duplicate ADMIT returns same receipt; different intent_hash same dispatch rejected; CLOSED refused; journal survives simulated disconnect; digest mismatch aborts install.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** manager + installer + units.
- [ ] **Step 4: Run** targeted; record G7 real-host checklist as unexecuted.
- [ ] **Step 5: Commit** `feat(agent): linux manager, systemd packaging, digest-verified installer`.

### Task D6W.1: Windows manager + WinSW packaging

**Files:**
- Create: `agent/manager/windows/nimbusops_manager.py` (pipe server), `agent/manager/windows/install.ps1`
- Create: `deploy/windows/nimbusops-agent-service.xml.template`, release manifest tooling
- Test: `backend/tests/provisioning/test_windows_manager_protocol.py` (framing/dedup via fake pipe)
- Real-host gate: G6/G7 (documented, not executed now)

**Interfaces:**
- Consumes: ADR-5.1 (WinSW pin/provenance), ADR-5.2 (pipe, peer SID, admission receipt), §8 Windows layout.
- Produces: manager implementing §15.4 messages over `\\.\pipe\nimbusops-manager-v1` with impersonation SID check; manifest tooling verifying WinSW/Python/agent digests before install; XML template with delayed autostart + onfailure backoff + stop timeout.

- [ ] **Step 1: Failing tests** — manifest tool refuses missing/mismatched digest; framing >64KiB rejected; duplicate dispatch dedup; receipt validation before START_ACTION; XML template renders with pinned values.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** targeted; record G6 digest confirmation + G7 real-host checklist as unexecuted.
- [ ] **Step 5: Commit** `feat(agent): windows manager, winsw packaging, manifest provenance`.

## Part 4 — Azure and dashboard (D7–D8)

### Task D7.1: Azure adapter (mock-gated)

**Files:**
- Create: `backend/app/services/provisioning/adapters/azure.py` (behind base interface), `backend/app/services/provisioning/adapters/local_windows.py`, `generic_linux.py`
- Modify: connection config loader (server-side file reference per §1)
- Test: `backend/tests/provisioning/test_azure_adapter.py`, `test_local_windows_adapter.py`, `test_generic_linux_adapter.py`

**Interfaces:**
- Consumes: D3.2 base adapter; ADR-5.4 (Run Command ≥2023-03-01, no secrets, IMDS bootstrap, ARM read per mutation); ADR-5.2/5.3 transports.
- Produces: adapters implementing `capabilities/discover/validate/dispatch/reconcile/request_cancel/diagnostics`; Azure grant-exchange route wiring (JWKS/issuer/audience/nbf/oid/ARM binding per §15.6); local Windows pipe client; generic Linux SSH client.

- [ ] **Step 1: Failing tests** (fake SDK/transport) — scope allowlist enforcement; no-secret assertion over serialized dispatch payloads (canary scan); UNKNOWN on timeout-after-send; stale vmId binding denied; missing identity → SETUP_REQUIRED; manager-auth router rejects cookie/agent bearer; GENERIC_LINUX missing channel → SETUP_REQUIRED.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** adapters with pinned SDK imports lazy-loaded (import error → SETUP_REQUIRED, not crash).
- [ ] **Step 4: Run** targeted + suite.
- [ ] **Step 5: Commit** `feat(provisioning): provider adapters with gated Azure enablement`.

### Task D8.1: Dashboard wizard, progress, history

**Files:**
- Create: `frontend/src/views/AddServerWizard.tsx`, `frontend/src/views/ProvisioningHistory.tsx`, `frontend/src/lib/provisioningClient.ts`, `frontend/src/lib/provisioningTypes.ts`
- Modify: `frontend/src/App.tsx` (routes), `frontend/src/views/HostDetail.tsx` (recovery actions from `allowed_actions`)
- Test: `frontend/src/views/__tests__/wizard.test.tsx`, `history.test.tsx`, `frontend/src/lib/__tests__/provisioningClient.test.ts`

**Interfaces:**
- Consumes: OpenAPI contract (typed client); design §10 UX states/accessibility; existing session/auth client patterns (active UX WIP NOT imported — implement on this branch's frontend state).
- Produces: wizard steps provider→target→configure→review→submit→progress→completion; nonsecret idempotency key persistence; event polling (≥2s, backoff); truthful states (loading/empty/denied/reconciling/failed/cancelled/success with evidence); history with filters+paging; keyboard/aria-live/focus per §10.

- [ ] **Step 1: Failing tests** — mock API per state; duplicate submit disabled + server-idempotent replay; reload resumes by job id; no secrets in localStorage (canary test); cancel dialog truthful; allowed_actions respected; accessibility assertions (labels, focus).
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** frontend suite + build.
- [ ] **Step 5: Commit** `feat(dashboard): provisioning wizard, progress, history`.

## Part 5 — Recovery and release evidence (D9–D10)

### Task D9.1: Recovery operations

**Files:**
- Modify: provisioning service (REENROLL/ROTATE/RESTART/DIAGNOSE operations over existing host_id + independently authorized mapping)
- Test: `backend/tests/provisioning/test_recovery.py`

**Interfaces:**
- Consumes: D4/D6; §11 runbook.
- Produces: recovery job types honoring: revoked/offline → independent channel only; never old-token authority; re-enroll clears revoked only at reviewed revision (§15.2); Docker ops quarantined across identity jobs.

- [ ] **Step 1: Failing tests** — revoked host recovery via independent channel succeeds with stable host_id; old credential denied throughout; uncertain remote outcome retains ownership; DIAGNOSE requires fresh job-bound proof.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** targeted + suite.
- [ ] **Step 5: Commit** `feat(provisioning): authorized recovery operations`.

### Task D10.1: Failure injection and full regression

**Files:**
- Test: `backend/tests_integration/test_provisioning_flow.py`, `backend/tests/provisioning/test_failure_injection.py`
- Modify: `docs/superpowers/specs/2026-11-17-sprint5-design-evidence.md` (results ledger)

**Interfaces:**
- Consumes: all previous.
- Produces: loopback end-to-end (fake adapter): wizard API flow → worker dispatch → managed enrollment → challenge receipts → SUCCEEDED; crash-point matrix; secret canaries across logs/argv/storage; full backend+agent+integration+frontend+build green at pinned revision.

- [ ] **Step 1: Failing e2e test** — happy path returns SUCCEEDED with real receipts only.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** harness + injection matrix.
- [ ] **Step 4: Run** full matrix; record evidence per class (A/B only; C/D remain gated).
- [ ] **Step 5: Commit** `test(provisioning): failure injection and end-to-end verification`.

## Rollback boundaries (per task)

- Each task commit is independently revertible (additive; no data rewrites). Schema migration failure → readiness report blocks provisioning, legacy flows continue. Worker/adapter defects → disable dispatch via config flag (documented per task), legacy monitoring unaffected. Frontend defects → routes removable without backend impact. C/D real-host tasks never run without G7 approval; their failure boundary is "no install performed" (journal + typed error).

## Acceptance criteria (release gate, after all tasks)

Design §13 table verbatim: every row's evidence class satisfied and recorded; C/D rows explicitly pending until G6/G7 evidence lands; no success claim beyond class A/B in this branch's CI.
