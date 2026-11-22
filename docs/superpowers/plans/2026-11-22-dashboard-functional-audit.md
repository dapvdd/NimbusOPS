# Dashboard Functional Audit Implementation Plan

> **For agentic workers:** Use executing-plans to implement task-by-task in this session.

**Goal:** Demonstrate the MVP honestly without requiring real provisioning.
**Architecture:** Preserve React/Vite and FastAPI contracts. Repair confirmed defects with regression tests; use disposable tests and mocked transport only for operational boundaries.
**Tech Stack:** React 18, TypeScript, Vitest, FastAPI, SQLAlchemy, pytest.
**Spec:** User's FULL DASHBOARD FUNCTIONAL AUDIT & REPAIR request in this session.

## Global Constraints
- Dedicated branch `dev/dashboard-functional-audit`; no push, merge or deployment.
- Never touch frozen acceptance checkout/database, root grants, spent markers or old job.
- No SSH installation, provisioning admission, new operational infrastructure or worker execution.
- Tests may create synthetic fixtures in isolated temporary test databases only.
- No visual redesign or authentication/safety weakening.

## Review Focus
- Partial health failures must not render ready or retain stale green probes.
- A late filtered response must not replace the current activity filter.
- Unregister must update fleet only after confirmed API success.
- Unknown setup outcomes must never appear as installation/enrollment success.
- Exit diagnostics must expose numeric status only, never remote output or secrets.

## Tasks
- [x] Inventory routes, baseline frontend tests and isolated branch.
- [x] Inspect route controls and API/tests; record coverage and limitations (exhaustive browser action coverage remains incomplete).
- [x] Add failing regressions for repaired truthful-state and interaction defects.
- [x] Implement minimal frontend fixes and rerun regressions.
- [x] Add safe numeric installer failure diagnostics with mocked subprocess regression tests; preserve reconciliation semantics.
- [x] Run frontend suite/build and backend suite/static checks in local isolated environment.
- [x] Exercise safe browser/API journeys; document unverified actions explicitly.
- [x] Independent review, pagination repair, full suites, route readiness matrix.

## Execution ledger
- Baseline frontend 162 pass; backend-only 379 pass/10 skip.
- Observed RED then GREEN: preflight JSON, uncertain job step/reason/diagnostic UI,
  partial readiness/stale green, logout rejection, stale fleet all-clear,
  activity obsolete response, unregister refresh, canonical deployments link,
  numeric exit capture/event/API allowlist. Timeout/invalid allowlist tests pass.
- Independent review: medium activity pagination busy-state regression reproduced
  RED then fixed; final frontend 174 pass and build PASS; Python 532 pass/11 skip.
- Deferred minor and rulings recorded in `docs/DASHBOARD_READINESS_AUDIT.md`.
- Remaining exhaustive audit/live-browser integration gaps explicitly retained.

## Execution
Native inline execution, per user's no-routine-approval instruction. Commit only this task's verified files if appropriate; never include acceptance evidence or unrelated changes. No push.
