# Dashboard Finalization Implementation Plan

**Goal:** Truthful presentation workflows against disposable live React/FastAPI processes.
**Spec:** User's Dashboard Finalization Sprint (six phases).
**Architecture:** Preserve existing stack; owner-scoped read-only job history, focused feedback repairs, isolated browser integration. No schema migration required.

## Constraints
Only dev/dashboard-functional-audit; preserve unrelated acceptance changes. No push/deploy, installer, provisioning admission/dispatch, sudo, preserved DB access or infrastructure changes. Synthetic fixture rows only in new scratch databases. No retry UI.

## Review focus
Ownership leaks, stale verification after failed polls, duplicate operational submissions after admission, browser cookie/CSRF mismatches, misleading partial-feed success.

## Tasks
- [x] Repair token feed, event recovery, manual proof and readiness with RED/GREEN regressions (frontend views/hooks/tests).
- [x] Repair deployment admission/tracking with preserved operation IDs and read-only recovery (Applications/tests).
- [x] Add owner-scoped paginated GET provisioning jobs and metadata; integrate discoverable history into AutomaticSetup; test access/empty/error/refresh.
- [x] Create isolated live API/Vite/Chromium harness with disposable operators, hosts, operations and fixture job; no API interception for core journeys. Expand safe browser controls and label fault mocks.
- [x] Resolve scoped B008/CAS typing; run full frontend/Python/build/format/lint/mypy/browser gates (imported-module typing limitations recorded).
- [x] Independent review, repair findings, update readiness matrix, commit verified cohesive changes (never push).

## Execution
Independent domains delegated with exclusive file ownership; coordinator owns history and integration. Each implementer must reproduce regression before fixes and report exact evidence. Review all combined changes and rerun gates.

## Resumption ledger

- 2026-11-22: User confirmed the four interruptions were quota-related and explicitly authorized resuming their existing sessions. Existing partial edits are preserved; backend history, feed reliability, dialog accessibility and disposable live browser work resume in their original exclusive scopes.
- Ruling: retain the existing delegated execution arrangement rather than restart inline — the user requested continuation of those interrupted agents; cost if wrong is duplicated context, mitigated by resuming original sessions and forbidding overlapping edits.
- Coordinator inspection found the deployment test file had replaced prior regression coverage. A separate exclusive deployment continuation must restore the baseline tests alongside new regressions and verify admitted-ID recovery across remounts.
- Dialog agent reports 9 focused tests and 194 full frontend tests passing; this is provisional until coordinator combined verification. Browser accessibility and assistive-technology behavior remain distinct from jsdom coverage.
- Integration contract: history API returns owner-scoped `{jobs, total}` with metadata consumed by `SetupHistory`; no secrets or mutating history controls. Live harness uses synthetic rows in disposable SQLite only, not the historical acceptance database.
- Coordinator found a terminal history inspection could expose “Add another server” while an unresolved confirmation existed, clearing that intent. Added regression: observed 1 failure/12 passes, suppressed reference-clearing controls while intent exists, then 13/13 passed (`npm test -- src/views/__tests__/automatic-setup.test.tsx`).
- Coordinator combined Python verification: `python -m pytest -q` → 542 passed, 11 skipped, 3 dependency deprecation warnings. Scoped Ruff and Black passed. Strict mypy for two changed modules passes with `--follow-imports=silent`; unrestricted imported-module checking still reports 24 errors in 6 other modules and is not globally clean.
- First live harness agent run reported 17 checks passed, no interception or browser JS errors. Viewer token-feed 403s were discovered; role gating and an expanded live rerun are in progress. Job-history pagination and real session-expiry are being added to the harness.
- Coordinator `npm test` combined run → 212 passed across 32 files (React Router future warnings only); `npm run build` → PASS, 70 modules. Deployment final edits and expanded browser run still require final gate/review before commit.
- Coordinator reran `python frontend/scripts/finalization-browser.py` → 18 passed, 0 failed; owned Vite/uvicorn stopped and disposable DB removed. Expanded coverage includes 50→65 setup history rows, foreign-owner 404, server-revoked session/relogin and no VIEWER token-feed 403s.
- Independent review identified Important busy-transition focus containment in ConfirmDialog; assigned RED/GREEN repair. Minor deferred: offset history paging under concurrent insertions may repeat an item; this remains a documented limitation (static fixture paging passes).
- Deployment agent restored 11 original tests and reports 24 combined Applications tests with operator/action-scoped sessionStorage recovery; final coordinator rerun and independent review pending. Persistence is same-tab only; interrupted POST without an admission response remains unknown.
- Commit `e2f8809`: verified owner-scoped read-only provisioning history API/tests and typing-only CAS result cast. No unrelated acceptance files staged, no push.
- Important dialog review fix: agent observed 4 RED regressions then 13 focused GREEN; coordinator combined `npm test` now 218 passed/32 files and fresh `npm run build` passed (70 modules). Actual Chromium local-only busy-transition component check is being added; it must not submit operational API writes.
- Deployment independent review found Important gaps: server-reported UNKNOWN not blocking lifecycle, unresolved deployment vs lifecycle cross-panel guard, delayed POST response across remount, and storage-read failure. Required single repair pass assigned with deferred-response/UNKNOWN RED→GREEN regressions. ADMIN→VIEWER must hide/stop admission polling without discarding ADMIN recovery references. Frontend is not yet ready to commit.
- Final minor (deferred): browser viewer check asserts no token 403s rather than all matching requests (unit test asserts requests); browser safety audit checks provisioning mutations, not every operational endpoint. Inspected journeys contain no operational writes, but this is not a comprehensive request-allowlist proof.
- Commit `235c4b5`: verified focused feed/manual/readiness/clipboard/dialog recovery and read-only setup history UI with preserved uncertain intents. Coordinator full frontend 218/32 and build passed before commit. Applications remains excluded while review fixes continue; browser harness/evidence docs will be a later cohesive commit.
- Commit `0cd4f96`: disposable live Chromium/Vite/FastAPI harness. Coordinator fresh rerun → 19 passed/0 failed, including real busy-dialog local-only component check with zero API requests. Artifacts `C:\Users\user\AppData\Local\Temp\opencode\nimbusops-real-browser-o2itlziq\`; owned processes stopped and disposable DB removed. Black/Ruff pass.
- Final review repair: 8 deployment regressions observed RED, then 32 Applications tests GREEN; original 11 retained. Coordinator final `npm test` → 226 passed/32 files, `npm run build` → PASS (70 modules), `git diff --check` → PASS. Shared pending/admission subscription covers delayed responses across SPA remount; server UNKNOWN and cross-panel uncertainty guard lifecycle writes; ADMIN references retained but hidden/not polled for VIEWER; storage read failure fails closed.
- Commit `84c8279`: admission recovery and review fixes. Limits: tab-scoped only; reload before returned ID requires reconciliation, with pending marker blocking resubmit; no actual deployment admission or container execution in browser. Scoped sprint complete with DEMO READY (bounded local synthetic read-only demo), not infrastructure/provisioning acceptance or repository-wide typing-clean status.
- Final post-fix coordinator reruns: `python -m pytest -q` → 542 passed/11 skipped/3 dependency warnings; `python frontend/scripts/finalization-browser.py` → 19 passed/0 failed, artifacts `C:\Users\user\AppData\Local\Temp\opencode\nimbusops-real-browser-z65m58gt\`, owned processes stopped/disposable DB removed. Branch/worktree preserved as explicitly requested, no integration menu needed because push/merge are prohibited.
