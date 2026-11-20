# RC2 Architecture Decisions

- Date: 2026-11-15
- Baseline: `v1.0.0-rc1` = `965be27b7e98fa7470c44a5f37864fd58798b3ce`
- Candidate: branch `rc2/hardening`, head `b3fb6a7` (plus this documentation commit)
- Recovery fix: `1e5709f` applied as `8a48256`; RC1 was not rewritten

Each decision below states the problem, the choice, the rejected alternative,
and the consequence. Numbers in parentheses are the audit defect ids.

## AD-1 Enrollment has exactly one credential and one explicit mode (F01, F08)

**Problem.** The endpoint silently accepted both `enrollment_token` and
`bootstrap_token`, and the agent always sent only `enrollment_token`, so the
documented secure flow could not work. A shared secret could also rotate an
existing host's credential by hostname.

**Decision.**
- The request carries exactly one credential; both present → 400
  `ENROLLMENT_MODE_CONFLICT` (ambiguous trust root is rejected, not resolved).
- `NIMBUSOPS_ENROLLMENT_MODE` is the deployment profile:
  `legacy` (shared token for **new** hosts only), `bootstrap` (shared path
  disabled; only single-use, hostname-scoped bootstrap tokens enroll),
  `disabled`.
- A shared secret never replaces an existing credential. Re-enrollment is an
  operator-issued bootstrap token; the host id is stable across it.
- The agent accepts the bootstrap token from `--bootstrap-token-file` or
  `NIMBUSOPS_AGENT_BOOTSTRAP_TOKEN`, never argv.

**Rejected.** "Try bootstrap, then fall back to legacy" — it makes the trust
root depend on request content and prevents any meaningful security test.

**Consequence.** Phase-4 removal of the legacy path is now a config change, not
a code rewrite. Operators must issue bootstrap tokens for re-enrollment.

## AD-2 Docker disablement is enforced at dispatch *and* at execution (F04)

**Problem.** Only `DEPLOY` was excluded at poll time; a queued START/STOP/
RESTART could still mutate a host after an operator disabled Docker. The agent
also discarded the heartbeat's `docker_enabled` flag.

**Decision.**
- Server: a disabled host claims **no** operation of any type. Queued work
  stays `QUEUED` (not lost, not failed).
- Agent: the last heartbeat flag is authoritative at execution time; when
  false, no Docker command runs and the result is `UNKNOWN` /
  `DOCKER_DISABLED`.
- In-flight (`RUNNING`) work is never force-terminated; the operation is
  reported honestly and the operator decides.

**Rejected.** Rejecting or cancelling queued work on disable — that would
destroy operator intent and produce misleading history.

**Consequence.** Two independent checks (control plane and agent) must both be
wrong for a mutation to run.

## AD-3 Ownership is proven by labels, not by name (F05)

**Problem.** Lifecycle operations checked only the `nimbusops-` name prefix.

**Decision.** Before START/STOP/RESTART the agent runs
`docker inspect --format {{json .Config.Labels}}` and requires
`nimbusops.managed=true` **and** `nimbusops.deployment=<exact id>`. Absent
container → FAILED; unreadable inspection → `UNKNOWN`/`VERIFY_FAILED`; wrong or
missing labels → FAILED and no mutation. DEPLOY refuses a name collision with
an unmanaged container, and refuses to recreate an owned one
(`CONTAINER_EXISTS`; use START/STOP/RESTART).

**Rejected.** Prefix-only checks with a name-collision warning — it still
permits mutating a container NimbusOps does not own.

**Consequence.** A deployment id is unique per (host, template), so the
deployment label also proves the expected host identity.

## AD-4 "Unknown" is a first-class state; success requires evidence (F06)

**Problem.** A failed or empty `docker ps` was converted into
`EXITED`/SUCCEEDED, and `Up (Paused)` was parsed as RUNNING.

**Decision.** Verification failure or absent output yields `UNKNOWN` with
`VERIFY_FAILED`; the backend never fabricates a terminal success. Paused is
`PAUSED`. Container state and HTTP reachability are separate fields
(`container_state`, `http_ok`).

**Consequence.** Operators see uncertainty instead of false confidence; UI and
API already render `UNKNOWN`.

## AD-5 Claims are fenced and results are compare-and-set (F07)

**Problem.** Dedup was SELECT-then-INSERT, "first write wins" was a status read
followed by assignment, and a timed-out claim could be re-delivered while a
delayed result was still in flight.

**Decision.**
- `deployment_operations.claim_generation` increments on every claim; the
  command carries it and the agent echoes it.
- Result recording is a conditional UPDATE on
  `id + host_id + status IN (QUEUED,RUNNING) [+ claim_generation]`.
  Exactly one submission wins; losers get `accepted=false` and the honest
  current status, and existing evidence is never overwritten.
- At most one non-terminal operation per deployment, enforced by the partial
  unique index `ux_ops_inflight_deployment`
  (`WHERE status IN ('QUEUED','RUNNING')`). Concurrent creators catch
  `IntegrityError`, re-select the winner, and return `deduplicated=true`.
- Bootstrap-token consumption and host creation commit in one transaction.

**Rejected.** Application-only locking (SQLite/Postgres differences, and a race
remains across processes) and "last write wins" (destroys evidence).

**Consequence.** The migration creates the index only when existing data has no
duplicate in-flight rows; otherwise it logs a warning and boot continues, so a
legacy database can never be blocked by data the operator must reconcile.

## AD-6 History is newest-first, server-filtered, offset-paged (F10)

**Decision.** `GET /operations` orders by `created_at DESC, id DESC`, applies
status/host/deployment filters before the window, accepts `offset`, and returns
a pre-window `total`. `count` remains the number of returned rows. The UI sends
the status filter to the server and appends older pages.

**Rejected.** Cursor pagination on `(created_at, id)` — better at very large
scale but unnecessary for the measured small-fleet scope, and it would add a
client contract the current UI does not need.

**Consequence.** Recent operations can no longer be hidden by a bounded window.

## AD-7 Health tells the truth; readiness fails (F12, F15)

**Decision.** `/health` stays HTTP 200 as a liveness signal but reports
`status=degraded` and `database=degraded` when the dependency check fails. A new
`/ready` returns 503 in that state for load-balancer routing. The payload
carries the real `VERSION` (`1.0.0-rc2`) and an immutable `build` from
`NIMBUSOPS_BUILD_SHA` (`unknown` when absent, never invented). The console shows
online/degraded/unreachable separately.

**Consequence.** Monitoring must distinguish liveness (`/health`) from
readiness (`/ready`); the release runbook and deployment probes should target
`/ready`.

## AD-8 The agent artifact is a real installable package (F09)

**Decision.** `agent/pyproject.toml` publishes `nimbusops-agent` 1.0.0rc2 with
the `nimbusops-agent` console script and declared dependencies;
`nimbusops_agent/__main__.py` makes `python -m nimbusops_agent` real. The
runbook uses the actual `NIMBUSOPS_AGENT_*` variables and the bootstrap-token
file flow.

**Consequence.** The documented commands now resolve to tracked code. Clean-host
installation is still unverified (see the readiness report).

## AD-9 Deliberately deferred (not silently dropped)

| Item | Status | Reason / required input |
|---|---|---|
| F03 durable execution receipts and result replay after a crash | PARTIAL | Claim fencing and single-winner results prevent stale/duplicate wins, but a *process* crash between effect and result delivery still needs a durable receipt store. Design decision required (agent-local journal vs server-issued receipt). |
| F11 fleet list N+1 and unbounded legacy shape | OPEN | Needs a bulk latest-metric query and a frontend pagination contract; no measured throughput target exists yet. |
| F13 `app_url` points at the operator's localhost | OPEN | Requires an approved host-specific access-endpoint design; removing the link is a product decision. |
| Runtime route-value upgrades for dev-tool advisories | OPEN | `react-router-dom` 6→7 and `vite`/`vitest` majors are breaking changes; see security acceptance. |
