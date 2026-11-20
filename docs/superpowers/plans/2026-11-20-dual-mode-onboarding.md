# Dual-mode onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Preserve manual enrollment and implement explicit, authorized SSH setup in isolation.
**Architecture:** Existing bootstrap API and agent protocol remain authoritative. A server-side target allowlist and fixed SSH commands feed a durable worker; preflight and explicit approval precede installation. Existing provisioning tables hold plans/jobs/events; no secret material is persisted.
**Tech Stack:** FastAPI, SQLAlchemy, SQLite, OpenSSH, React/TypeScript, pytest, Vitest.
**Spec:** User decision “DECISION APPROVED — DUAL-MODE ZERO-TOUCH ADD SERVER”, 2026-11-20 (requirements recorded below).

## Global Constraints
- Automatic Setup recommended; Manual Bootstrap remains available.
- Ubuntu 24.04 amd64, telemetry only; never overwrite identity or silently reenroll.
- Existing Katrina URL, database, Azure hosts and DavidLab production immutable during development.
- Credentials referenced server-side only; SSH strict host-key checking, allowlisted targets, no browser commands.
- No deployment, push or merge. Real disposable-VM acceptance is mandatory for upgrade GO.

## Review Focus
- SSH disconnect after submission must never trigger blind reinstall.
- Two aliases for the same machine must not bypass exclusion.
- Changed target identity or policy invalidates confirmation.
- Worker restart during install requires reconciliation, not redispatch.
- Consumed token alone is not success without fresh heartbeat and telemetry.

## Tasks
### Task 1: Manual compatibility and baseline
Files: `backend/app/schemas/__init__.py`, `backend/tests/test_utc_wire_timestamps.py`, manual onboarding existing tests.
- [ ] Add regression test for deployed UTC serialization; observe RED, preserve focused hotfix, observe GREEN.
- [ ] Run Python and frontend baseline suites; keep pinned artifact and manual protocol unchanged.

### Task 2: Authorized SSH transport
Files: `backend/app/provisioning/ssh.py`, `backend/tests/test_provisioning_ssh.py`.
Produces: target-policy loader; fixed read-only preflight and pinned-install transport with secret input via stdin only.
- [ ] Test allowlist rejection, strict SSH options, invalid policy, preflight incompatibility/identity guards and fixed argv, RED→GREEN.
- [ ] Reject alias machine bindings in service and never accept browser addresses/commands/credentials.

### Task 3: Durable API and worker
Files: `backend/app/api/provisioning.py`, `backend/app/services/provisioning.py`, `backend/app/provisioning/worker.py`, `backend/app/main.py`, tests.
Consumes: target policy and SSH transport. Produces: targets/preflight/confirm/job/retry API and separate worker CLI.
- [ ] Test ADMIN enforcement, expiration, changed identity/policy, atomic single-use confirmation and duplicate exclusion, RED→GREEN.
- [ ] Test token-linked fresh telemetry verification, failed/ambiguous dispatch and restart fail-closed behavior, RED→GREEN.
- [ ] Test retries revalidate without overwriting identity; append sanitized audit events.

### Task 4: Dual-mode UI
Files: `frontend/src/views/Onboarding.tsx`, `frontend/src/views/AutomaticSetup.tsx`, API module and tests.
Consumes: provisioning API. Produces: recommended automatic selector, reviewed target/change summary, explicit confirmation, job polling and safe retry; unchanged manual wizard.
- [ ] Test separated methods and confirmation/error/progress states, RED→GREEN.
- [ ] Run Vitest, TypeScript/build and Python suites.

### Task 5: Upgrade readiness package
Files: `docs/DUAL_MODE_UPGRADE_READINESS.md`, operator policy example.
- [ ] Review full diff; document results and remaining gaps, no success claims for unavailable VM tests.
- [ ] Prepare online backup/integrity, schema rehearsal, preservation checks, health gates and rollback; no live execution.
- [ ] Deliver GO/NO-GO package, no push/merge/deployment.

## Execution ledger
- Baseline: native isolated worktree `dual-mode-onboarding`, detached at `8203d461fb8edd93e79351a7fe129832f5a726f1`. Original dirty worktree untouched.
- Python baseline: 459 passed, 1 skipped, 3 dependency deprecation warnings (104.35s).
- Ruling: user explicitly authorized immediate isolated execution; no additional design gate. No real VM endpoint/credential authorized yet; local tests do not substitute for clean-VM acceptance.
- Ruling: execute inline; no subagents unless final review skill requires one. Retain ledger and uncommitted changes for review; no push/merge.
- Restart continuation: recovered existing edits, resumed at pending SSH install test; did not repeat baseline implementation.
- UTC regression RED→GREEN using focused schema from c0255d4; SHA compatibility will be checked before upgrade.
- Implemented policy/preflight, fixed pinned install transport, durable plans/admission/reconciliation, ADMIN API, method selector and initial automatic UI.
- Python full suite after implementation: 477 passed, 1 skipped, 3 dependency warnings (70.43s). Frontend baseline: 146 passed; initial new automatic and existing manual tests: 7 passed. Build passed.
- Ruling: only pre-dispatch failures can retry with a new preflight/approval. Admitted/uncertain operations retain ownership and require operator reconciliation; no automatic reinstall.
- Remaining: broaden failure/retry/UI coverage, review security, frontend final suite/build, clean-VM acceptance (no disposable target supplied), readiness package.
- Latest full Python regression: 479 passed, 1 skipped, 3 warnings (68.56s); full frontend 147 passed; frontend build passed; additional confirmation-flow targeted tests 2 passed. `git diff --check` passed with CRLF warnings.
- Created `docs/DUAL_MODE_UPGRADE_READINESS.md`: NO-GO pending review/security and real disposable-VM acceptance; includes proposed backup/migration/health/rollback, no live commands executed.
- Fresh-context reviewer dispatched read-only against uncommitted candidate. Await findings before declaring candidate complete.
- Final frontend run after confirmation test: 148 passed (25 files, 8.16s). Strict mypy failed (new API/worker annotations plus existing imported-module errors); Black check failed (4 new files need formatting). Recorded as unresolved gates in readiness package; no completion claim.
- Independent review found five important blockers (ownership release race; token conflict/atomicity; concurrent reconciliation; target token file persistence; lost browser job reference).
- Fix pass RED→GREEN: conflict survival, kernel worker-lock exclusion, conditional retry release, tmpfs installer adapter, nonsecret session job recovery. Python suite 484 passed, 1 skipped (72.85s). New files formatted; scoped strict mypy passes four production modules with imported errors silenced. Ruff dependency-default findings remain.
- Ruling: single-host local SQLite workers serialized by shared kernel lock rather than distributed leases; unsupported distributed workers must not be deployed. Automatic bootstrap uses restricted tmpfs, not persistent /var/lib; verify swap policy before acceptance. SessionStorage contains only job UUID, never credentials.
- Final verification after fix/formatting: Python 484 passed, 1 skipped, 3 warnings (76.16s); frontend 148 passed (9.49s); TypeScript/Vite build passed; Black five files unchanged. NO-GO remains for real VM/schema/privilege/dependency/static coverage gates.
