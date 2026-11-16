# Classroom Authentication Implementation Plan

> Execute inline using executing-plans and test-driven-development. Approval: user approved the Phase 0 compatibility plan and explicitly instructed continuous implementation.

**Goal:** Application-wide human login and read-only VIEWER access without touching the running demo.
**Architecture:** Extend existing operators and hashed sessions with a separate cookie login interface. Preserve legacy bearer APIs and agent authentication. Protect operational reads by dependency; all privileged writes remain ADMIN-only.
**Tech stack:** FastAPI, SQLite, React/Vite, Argon2 via argon2-cffi.
**Spec:** Approved Phase 0 compatibility plan in conversation, narrowed final scope in user approval.

## Constraints
- Separate worktree, private database, dedicated loopback preview ports; no live migrations/restarts.
- Exactly one classroom viewer; password entered privately, never in source or reports.
- No user-management features, no real enrollment or Docker operations.
- Preserve old operator hashes, host credentials and history.

## Review focus
- Cookie versus bearer ambiguity must not bypass CSRF.
- Expired/revoked cookies must not restore a session.
- Agent credentials must not authorize human reads or vice versa.
- Cross-origin login/logout must fail; HTTPS cookie configuration must be explicit.
- Viewer must not mutate simulated infrastructure through alternate frontend controls.

## Tasks / execution ledger
- [x] 1. Baseline: install isolated dependencies; run backend/frontend tests before changes. 264 passed/1 skipped Python; 56 frontend.
- [x] 2. Backend: watched missing read/cookie/Argon2/setup behavior fail, implemented and verified. Final whole Python suite: 287 passed, 1 skipped; 3 dependency deprecation warnings.
- [x] 3. Frontend: watched login/role tests fail; implemented session/role boundary. Final 58 passed; production TypeScript/Vite build passed. React Router future warnings remain.
- [x] 4. Private database contains exactly presenter-local ADMIN and viewer VIEWER; no hosts or host credentials copied. Chromium ADMIN/VIEWER login/refresh/logout passed, no page exceptions or password console leaks. Live runtime state, Docker-off state and listener identities unchanged; health ok, telemetry reached normal 1440 retention.
- [x] 5. Fresh reviewer found simulated-remove role gap; regression RED then GREEN. Deferred two operational setup minors documented. Preview ready; integration HOLD pending explicit approval.

## Rulings
- Carry forward source-only dirty demo changes into new worktree; do not copy deploy/runtime state.
- Retain legacy bearer login for API compatibility; browser uses new cookie-only session endpoints with no bearer token in responses.
- Protect reads unconditionally in feature branch, not behind an opt-out auth flag.
- No host schema changes are needed; existing operator/session tables are sufficient.
- Native tool started from older commit; aligned new worktree to f931003 and recopied selected source files. Baseline then passed.
- Existing read-contract tests now use actual VIEWER sessions; no production auth bypass or opt-out flag.
- Preview contains existing ADMIN row copied read-only, not host credentials or telemetry; empty fleet intentional.
- Review: Important simulated removal fixed with RED regression. Deferred minors: setup database-path enforcement; launcher API-target enforcement.
