# Full MVP RC Implementation Plan

> **For agentic workers:** Use executing-plans for coordinator implementation and independent scoped workers/reviewers. User explicitly authorized continuous execution without another approval round.

**Goal:** Complete all independently executable Full MVP repairs and verification, retaining real Ubuntu/Docker acceptance as mandatory externally authorized gates.

**Architecture:** Start at dashboard `7194f10`, retain its pinned dual-mode installer and cookie-authenticated UI. Integrate missing durable agent recovery separately; add redacted provisioning phase evidence without treating transport termination as remote rollback. Use disposable databases and owned processes only.

**Tech Stack:** Python/FastAPI/SQLAlchemy/SQLite; Python agent; React/TypeScript/Vite; Chromium.

**Spec:** Product owner's FULL MVP COMPLETION PROGRAM (M0–M5), supplied 2026-11-22.

## Global Constraints
- No push, main merge, deployment, historical job retry, protected artifact changes, approval rearm, or snapshot restore.
- Preserve approved UI, authentication, TLS verification, sudo restrictions, agent identity and unrelated work.
- Privileged Ubuntu and actual Docker acceptance require separate authorization and fresh state.
- Exact historical installer failure is unknown: preserved report records intentionally discarded output.

## Review Focus
- Lost transport after admission must never redispatch an installer.
- Raw installer output may contain credentials; persist only allowlisted codes and numeric exit status.
- Agent result submission failure/restart must not repeat container execution.
- Revoked/foreign identities and duplicate enrollment must fail closed.
- Mock/synthetic/local browser results must not be labeled real-host acceptance.

## Task 1 — M0 integration baseline
- [x] Discover worktrees, revisions, dirty paths and divergent feature lines read-only.
- [x] Create native worktree and `integration/full-mvp-rc` from `7194f10`.
- [ ] Run Python/frontend baseline before production changes.
- [ ] Cherry-pick main hygiene `adf459e` and durable recovery `41c9af1`; preserve current UTC implementation.
- [ ] Record inventory and semantic disposition of competing private/classroom branches.

## Task 2 — M1 installer diagnostics and recovery
Files: `backend/app/provisioning/ssh.py`, `worker.py`, `backend/tests/test_provisioning_ssh.py`, `test_provisioning_jobs.py`.
- [ ] Investigate preserved local reports and current transport; never access historical remote state.
- [ ] Add failing tests for phase checkpoints, exit-status reporting, timeout, disconnect and redaction.
- [ ] Implement fixed allowlisted checkpoint protocol; preserve fail-closed uncertainty and one-shot CAS.
- [ ] Run provisioning suites; document exact historical unknown and reproducible local defects; commit.

## Task 3 — M2/M3 agent monitoring and Docker recovery
Files: `agent/nimbusops_agent/worker.py`, `main.py`, agent/backend integration tests.
- [ ] Integrate durable outcome journal and run restart/redelivery/resource-isolation tests.
- [ ] Exercise enrollment, replay rejection, heartbeat/telemetry/status transitions on disposable local backend.
- [ ] Exercise Docker contract/dedup/reconciliation tests; probe local Docker availability without installations.
- [ ] Repair demonstrated defects test-first; commit cohesive changes.

## Task 4 — M4 integrated verification
Files: `frontend/scripts/finalization-browser.py`, scoped additional integration harness/tests.
- [ ] Run real Chromium/Vite/FastAPI journeys against disposable state.
- [ ] Verify backend/agent restart and interrupted submissions with owned local processes or deterministic fixtures.
- [ ] Run complete Python/frontend suites, build and static checks; record exact evidence boundaries.

## Task 5 — M5 RC gates and operator documentation
Files: `docs/FULL_MVP_RC_STATUS.md`, `docs/FULL_MVP_OPERATOR_RUNBOOK.md`.
- [ ] Verify disposable migrations, backup/restore and security/deployment configuration within local authorization.
- [ ] Independent code review; fix findings and rerun affected gates.
- [ ] Record commits, matrix, P0/P1/P2 gaps and one minimal consolidated fresh Ubuntu/Docker authorization request.
- [ ] Commit verified development work locally; final verdict BLOCKED unless every real-host criterion is met.
