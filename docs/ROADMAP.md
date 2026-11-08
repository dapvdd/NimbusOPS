# NimbusOps Roadmap

All functionality below is **planned**. Acceptance criteria are future gates,
not reported test results. The [PRD v1.1 digest](PRD.md) provides requirement IDs.
The phase breakdown below comes from the Phase 0 assignment; product milestones
M0–M4 and versions come from PRD section 21. No dates are promised.

## Phase 0 — Repository Foundation

Acceptance criteria:

- Inspect branch, working tree, existing files, and history before editing.
- Provide README, architecture, roadmap, contribution guidance, and traceable PRD
  documentation (or an explicit missing-source notice if unavailable).
- Reserve `frontend/`, `backend/`, `agent/`, and `infra/` without application code.
- Cover Python, Node.js, environments, outputs, local databases, and secret files
  in ignore rules. Add environment examples only when variables are defined.
- Validate document links/structure, whitespace, change scope, and sensitive content.
- Commit reviewed files locally on `docs/nimbusops-foundation`; do not push or deploy.

Repository completion is distinct from M0, which requires group/lecturer approval
of PRD and architecture. The supplied source's draft status is preserved.

## Phase 1 — Single-host monitoring

Scope: first portion of v0.1; FR-01/02, monitoring portions of AC-01/02/06.

Acceptance criteria:

- One isolated Ubuntu VM is identified and reports actual CPU, RAM, and disk data
  through an authenticated agent-to-server path to the dashboard.
- Dashboard accessibility is evidenced with a screenshot and HTTP response.
- Compare timestamped dashboard readings against OS measurements using documented
  units, sampling intervals, and tolerances agreed before testing.
- Disconnect the agent and verify offline/stale indication within the documented
  threshold; reconnect and verify fresh data replaces stale readings.
- Show empty/error states honestly; use no fabricated metrics as demonstration proof.

Entry: confirm PRD direction and Phase 1 ownership; choose isolated host and
control-server placement, authentication, metric definitions, and connectivity.

## Phase 2 — Docker inventory and Nginx deployment

Scope: completes v0.1 / M1, FR-03–07 and AC-01 through AC-09.

**Status: implemented on `feat/docker-deployment-mvp` with automated tests;
real-Docker live verification BLOCKED on the development machine (no Docker
Desktop/WSL; nothing installed without authorization). See
docs/PHASE2_VERIFICATION.md.**

Implementation record (vs the acceptance criteria below, which require the
Ubuntu VM):

- Approved Nginx template (`nginx-demo`, image `nginx:1.27-alpine`, host
  port 8080) seeded in the backend catalog; `GET /api/v1/templates` lists it.
- Dashboard Applications view: host selection, template selection, Deploy
  with live operation progress, Start/Stop/Refresh lifecycle controls,
  explicit states for pending/running/failed/unknown/stopped and unreported
  container state.
- Durable operations with ids, timestamps, evidence, sanitized errors;
  states QUEUED/RUNNING/SUCCEEDED/FAILED/UNKNOWN; SUCCEEDED only on agent
  evidence (`docker ps` + HTTP probe result recorded by the agent).
- Duplicate protection: same-host-same-template deploy returns the in-flight
  operation (idempotent); unique (host, template) deployments.
- Agent executes only allowlisted op types/templates on `nimbusops-*`
  labeled resources via constrained CLI argv; monitoring is unaffected by
  Docker unavailability.
- Automated evidence: 93 Python tests + 27 frontend tests passing,
  including Phase 2 backend (18), agent Docker/worker (25), and
  backend↔agent integration (5, Docker mocked).
- Remaining for full AC pass: run on the Ubuntu VM with a real Docker
  Engine (inventory vs `docker inspect` comparison, HTTP 200 evidence,
  stop/unavailability evidence, deliberate-failure evidence, unrelated
  container before/after evidence).

Acceptance criteria:

- Compare managed inventory with Docker inspection on the Ubuntu VM.
- Deploy one approved Nginx template from the dashboard; record operation ID,
  verified running container, reachable URL, and HTTP response.
- Stop and start the demo through the dashboard; verify container transitions and
  application unavailability/recovery respectively.
- Show genuine failure code/message, timestamp, and operation ID for a deliberately
  induced failure. Show `UNKNOWN` when the result cannot be verified.
- Reject unauthorized templates and attempts to control a non-demo container;
  capture before/after evidence showing unrelated containers are unchanged.
- Authenticate all mutations; verify repeated requests cannot blindly execute twice.
- Demonstrate all PRD AC-01–09 together and record reproducible evidence.

Operation history (FR-08) is a Should requirement; agree its minimum scope without
silently making the full future audit system a v0.1 prerequisite.

## Phase 3 — Multi-host management

Scope: v0.2 / M2, FR-09.

Acceptance criteria:

- Register two distinct local hosts and show their identities, metrics, and status.
- Select either host and verify a deployment on each with container/HTTP evidence.
- Verify actions target only the selected host and do not change the other host.
- Disconnect one host and verify the other remains observable and manageable.
- Document and test retry/attempt tracking and duplicate-execution handling needed
  for two-host operation; evaluate persistence needs with evidence.

## Phase 4 — Hybrid private-public infrastructure

Scope: v0.3 / M3, FR-10; gated by provider access and lecturer approval.

Acceptance criteria:

- Manage at least one private host and one real public-cloud VM from the same
  dashboard using the same agent protocol.
- Demonstrate authenticated, secure cross-network communication with no exposed
  Docker TCP API, and verify monitoring and Nginx lifecycle on both hosts.
- Record provider, approved budget, network topology, access policy, and teardown
  responsibility before provisioning under separate authorization.
- Test disconnection/reconnection across environments without false healthy status.

If public-cloud access fails, obtain lecturer agreement on a fallback. Document the
limitation explicitly; an isolated local simulation does not pass the real hybrid gate.

## Phase 5 — Advanced reliability and security

Scope: optional v1.0 / M4, FR-11/12, after core workflow stability.

Acceptance criteria:

- Demonstrate operator/viewer authorization with allow/deny policy tests, including
  denied viewer mutations.
- Verify audit and operation history identify actor, host, action, time, and outcome
  without logging credentials.
- Revoke/rotate an agent credential and verify old credentials are rejected.
- Demonstrate bounded retry/reconciliation after interruption without duplicate
  mutations; record final verified or unknown outcome.
- Back up and restore agreed data to an isolated target; compare restored data and
  record a reproducible recovery drill. Restic/MinIO are PRD future candidates.

HA, Kubernetes, autoscaling, and automatic provider provisioning require separately
validated scope; they are not implicit acceptance criteria here.

## Evidence and progression

For each gate, record environment, revision, scenario, expected result, actual
result, timestamp, and sanitized supporting evidence. Screenshots alone do not
prove Docker or HTTP state. Obtain group review before declaring a milestone
complete. Phase 0 delivery stops at its local commit; Phase 1 requires a new task.
