# Onboarding Reliability Implementation Plan

> **For agentic workers:** Use executing-plans, inline implementation with one final fresh-context review.

**Goal:** Resolve acceptance findings A/B/C with regression tests, without changing enrollment architecture.
**Architecture:** Reuse existing ProvisioningRequest for actor-scoped confirmation keys and job recovery. Bind existing ownership/target rows in the bootstrap consumption transaction, fencing on job/generation. Persist browser confirmation intent before POST; distinguish terminal/missing references from uncertain active jobs.
**Tech Stack:** FastAPI, SQLAlchemy/local SQLite, React/TypeScript, pytest/Vitest.
**Spec:** User's FINAL ONBOARDING RELIABILITY FIX SPRINT directive (A/B/C).

## Constraints
- Current isolated worktree only; preserve ruff-results.json and unrelated changes.
- No live access, deployment, push, merge, dependency upgrades or protocol changes.
- Reuse existing tables; agent/installer bytes unchanged; no release rebuild needed unless those inputs change.
- Katrina and real-VM acceptance remain NO-GO.

## Review focus
- Reused key with changed payload must conflict, not return unrelated authority.
- Recovery must work after approval expiry/policy removal without redispatch.
- Cross-operator recovery/read/retry must not expose another operator's job.
- Manual tokens issued before automatic reservation must not bypass ownership at consumption.
- Storage failure must prevent dispatch; ambiguous jobs must not be silently dismissed.

## Task A: durable confirmation and recovery
Files: services/provisioning.py, api/provisioning.py, api/provisioning.ts, AutomaticSetup.tsx; focused backend/frontend regressions.
- [ ] Write/run failing duplicate, changed-key payload, lost-response/reload, unauthorized and concurrent confirmation tests.
- [x] Atomically persist actor/route/key/request-hash/job using existing requests table; CAS losers recover winner.
- [x] Add ADMIN + requester-scoped recovery/read/retry; browser persists intent before POST, recovery GET never dispatches.
- [ ] Run focused suites and record evidence.

## Task B: cross-mode ownership
Files: services/enrollment.py, services/provisioning.py, services/hosts.py, api/agents.py, provisioning/worker.py; ownership regressions.
- [ ] Write/run failing automatic binding, manual conflict/consumption, stale generation and rollback tests.
- [ ] Serialize local SQLite ownership checks with writes; only matching worker job/generation bypasses its reservation.
- [x] Bind token result, target and ownership before enrollment commit; preserve host IDs/credentials and manual behavior.
- [ ] Run focused plus cross-process tests; record evidence.

## Task C: local reference lifecycle
Files: AutomaticSetup.tsx and tests.
- [ ] Write/run failing terminal add-another, missing-job, uncertain-job protection regressions.
- [ ] Add terminal local-reference clearing and explicit missing-reference recovery without automatic reinstall.
- [x] Run frontend suite/build.

## Final verification
- [ ] Full Python/frontend/build, scoped static/secret/diff checks; independent whole-change review.
- [ ] Update findings/readiness evidence, focused local commit after verification; no remote action.

## Evidence ledger
Initial HEAD f4c10150764ea78172ebfa37f2c35a12a2acedf2; tracked clean.
Root causes confirmed: unused existing requests table; ownership.host_id never populated; inner enroll_host commits precede token-result linkage; persisted job hides selection indefinitely.

- A backend RED: 3 expected failures (missing idempotency parameter / rejected key field); GREEN: replay/payload/authorization API gates passed.
- B RED: manual consumed reserved hostname; automatic host_id remained null; stale released token enrolled; legacy path bypassed reservation. Each reproduced before its fix, then passed.
- C RED: missing recovery method, absent terminal/missing-reference actions; GREEN: 7 UI tests pass, including response loss/same-key and storage fail-closed characterization.
- Four-process same-key confirmation returns one job/request; four-process bootstrap consumption creates one host/credential version 1 in both modes (11 focused backend tests pass).
- Full first run: 496 passed / 1 skipped / 3 dependency warnings (collected before 2 additional process cases); frontend 153 passed, build passed. Final rerun required after review.
- Ruling: reuse existing ProvisioningRequest, no migration/agent rebuild — source inputs to immutable archive are unchanged; cost if wrong: provenance would need rebuilding if agent/installer inputs later change.
- Ruling: SQLite writer reservation via a no-row UPDATE before ownership reads — supported single-host local SQLite only, not distributed SQL; cost if wrong: unsupported database locking semantics need their own implementation/testing.
- Ruling: old manual-token conflict test issues token before automatic reservation — issuance after reservation must now reject earlier; cost if wrong: worker conflict coverage would miss the intended preexisting-token scenario.
- Reviewer running read-only on complete changes; no live operations.
- Review returned two Important edge cases: rejected/no-job intents trapped the browser and mixed-case policy hostname failed host binding. Both reproduced RED, then fixed with explicit rejected-intent escape only after definitive POST rejection plus authenticated lookup 404, and canonical hostname handling. Focused GREEN: 12 backend / 8 UI.
- Full-suite-only process tests initially failed (2 failed/496 passed): child processes inherited environment rather than parent's cached hashing configuration, so all tokens were unrecognized. Test harness now passes the effective synthetic pepper into spawned children and clears their settings cache. No production credential change. Final full rerun pending.
- Ruling: clearing rejected intent requires POST rejection AND subsequent authenticated no-job lookup — a lone recovery 404 could race an in-flight confirmation; cost if wrong: ambiguous approvals might lose browser tracking.
- Final review fix pass completed; no second reviewer dispatch. Deferred minors: inherited malformed-policy handling; existing lint/static limitations remain recorded.
- Final frontend suite: 154 passed / 25 files; TypeScript/Vite build passes. Scoped strict mypy and Black pass 3 modified modules; diff whitespace passes.
- Final full Python: 499 passed / 1 POSIX-on-Windows skip / 3 dependency deprecation warnings; focused API/jobs/reliability 26 passed. Both reviewer Important findings fixed RED→GREEN and full suites green. A/B/C complete for local regression scope.
- Integration disposition: retain current detached worktree and focused local commit only, as authorized; no push/merge/deployment. Scratch ruff-results.json preserved.
