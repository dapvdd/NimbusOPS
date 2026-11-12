# Phase 5 — Infrastructure Orchestration Acceptance

Date: 2026-11-12 · Branch: `feat/autonomous-phase4-6` · Scope: mission §4 mapped to PRD FR-03/FR-05/FR-08 as planned.

## Requirements traceability

| Requirement | Status | Evidence |
| --- | --- | --- |
| Docker container inventory | PASS (new) | agent: test_inventory_and_restart (6) parses containers incl. managed/deployment labels, typed failure when docker missing; backend: test_inventory_api (5) — heartbeat ingest, replace-on-report, 404 `INVENTORY_NOT_FOUND` when never reported, `age_seconds` honesty, last snapshot survives inventory-less heartbeats |
| Container start/stop | PASS (pre-existing) | Phase 2 suites + integration flow |
| **Container restart** | PASS (new) | agent: RESTART allowlisted, managed-prefix gate, verify-after (Up check); backend: test_restart_op (4) — 202 QUEUED, docker-disabled → 403 `DOCKER_NOT_AUTHORIZED`, VIEWER → 403, agent poll claims RESTART with template |
| Approved deployment templates | PASS (pre-existing) | seed_templates, allowlisted images, agent double-checks image allowlist |
| Per-host Docker authorization | PASS (pre-existing + re-pinned) | docker_enabled default-off, server 403 + agent gate |
| Durable operation queue | PASS (pre-existing) | deployment_operations table, QUEUED→RUNNING claim, terminal ops never re-delivered |
| Operation status + history | PASS (new) | test_operation_history (8): `GET /operations?host_id&status&deployment_id&limit` filters + bounds + deterministic order; `GET /operations/{id}/events` append-only, id-ASC; unknown → 404; sanitized (no token material) |
| Idempotency + retry | PASS (pre-existing) | inflight dedup returns same op (deduplicated=true); claim-timeout requeue |
| Timeout + stale-op recovery | PASS (pre-existing) | reconcile_timed_out_ops + reconciler loop (I4) |
| Host capability checks | PASS | docker_enabled per host; inventory op safe on any host |
| Destructive-action confirmation | PARTIAL | API enforces ADMIN + explicit op endpoints; UI confirm modal exists for unregister; **restart/stop buttons in UI do not add an extra confirm dialog yet** — ADMIN-only dispatch is the server-side control; recorded as Minor UI gap |
| Per-operation audit | PASS (new + pre-existing) | operation_events append-only (CREATED/CLAIMED/RESULT/TIMED_OUT) |
| Concurrent op safety | PASS | single inflight per deployment (dedup), atomic claim (Phase 3B) |
| Offline-host behavior | PASS | ops queue until agent polls; reconciler recovers stale claims; natural reconnect verified live (Phase 3B evidence) |

## Architecture guarantees (mission §4)

- **No remote shell:** agent invokes docker via fixed argv `subprocess` (no
  shell=True anywhere in agent code). Pinned by
  `test_container_name_stays_single_argv_element` and the hostile-name pins
  (`;`, `$()`, backticks, `--privileged`, spaces).
- **Allowlist only:** DEPLOY/START/STOP/RESTART/INVENTORY; anything else →
  `UNAPPROVED_OPERATION`. Managed-prefix gate on every container-name op.
- **ADMIN authorization:** all dispatch endpoints require ADMIN session.
- **Identity validated at dispatch:** op carries server-side host_id from the
  deployment record; agent authenticates per-host token at poll.
- **No duplicate execution after reconnect:** claim-on-delivery + terminal
  states + claim-timeout reconciler (no re-delivery of terminal ops).
- **Leases:** `claimed_at`/`timeout_at` + reconciler = operation lease.
- **Failure/rollback behavior:** FAILED ops record error_code/error_message;
  DEPLOY verifies container up + optional HTTP probe; unverifiable → UNKNOWN
  (never fake SUCCEEDED). Rollback = operator re-dispatch (documented).

## UI deliverables

| Item | Status | Evidence |
| --- | --- | --- |
| Fleet-wide container overview | PARTIAL | inventory API + HostOut carry it; per-host inventory view is API-first (UI card deferred — Minor) |
| Per-host operation controls | PASS (pre-existing) | ServerDetail deploy/start/stop + new RESTART endpoint |
| Operation progress + status | PASS (new) | Activity.tsx real history + status filter |
| Clear failure messages | PASS (new) | error_code + error_message rendered per op |
| Confirmation for risky actions | PARTIAL (see above) | unregister confirm exists; restart confirm deferred |
| Audit/history interface | PASS (new) | Activity view = history API; events available via API |

## Test summary for this phase

- New: agent `test_inventory_and_restart.py` 6 + `test_inventory_heartbeat.py` 3;
  backend `test_inventory_api.py` 5 + `test_restart_op.py` 4 +
  `test_operation_history.py` 8; frontend `activity.history.test.tsx` 4.
- Full suites: backend/agent **212 passed**, frontend **48 passed**, build green.

## Explicitly not executed

- **Disposable Docker-environment integration** (real docker daemon): the
  program's Windows host runs no Docker daemon; docker-exec paths are proven
  with the same runner-injection technique used by the existing (passing)
  Phase 2 docker tests. Marked BLOCKED (environment), not skipped.

- **No production DavidLab Docker operations**: zero ops dispatched to
  production throughout (Phase 3B evidence stands).

## Verdict

**Phase 5: PASS** (two PARTIAL items are Minor UI gaps, documented in
NIMBUSOPS_V1_RELEASE_CANDIDATE.md known limitations).
