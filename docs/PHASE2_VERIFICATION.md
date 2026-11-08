# Phase 2 Verification Report — Docker Deployment MVP

Branch: `feat/docker-deployment-mvp` (from Phase 1 commit `c9bd011`).
Date: 2026-11-08. Environment: Windows 11 development machine
(Python 3.13.7, Node 24.15.0). **No Docker Engine exists on this machine**
(docker.exe absent from PATH and Program Files; no Docker service; WSL not
installed). Per the Phase 2 brief §12, Docker was NOT installed and
real-Docker verification is reported as **BLOCKED**; everything else was
implemented and verified with mocked-Docker tests labeled MOCKED below.

## 1. Docker prerequisites (for a verifying machine)

- Docker Engine on the managed host, `docker` CLI on the agent's PATH,
  daemon reachable via local socket. No root-only setup beyond normal
  Docker group membership. Never expose the Docker socket over TCP.
- Control server reachable from the agent (HTTPS/tunnel across networks;
  loopback OK locally).
- Host port 8080 free for the Nginx demo (template constant).

## 2. Approved Nginx template

| Field | Value |
| --- | --- |
| Key | `nginx-demo` |
| Image | `nginx:1.27-alpine` (pinned; allowlisted in backend seed AND agent) |
| Container port | 80 |
| Host port | 8080 |
| Container name | `nimbusops-nginx-demo-<host-id[:8]>` (deterministic) |
| Labels | `nimbusops.managed=true`, `nimbusops.deployment=<deployment-id>` |
| Mounts / privileges | none; `--restart no`; published port only |

Seeded idempotently at backend startup (`services/deployments.seed_templates`).

## 3. Deployment workflow (implemented end-to-end)

1. Operator opens **Applications** view, selects host + `nginx-demo`,
   clicks **Deploy**.
2. Backend validates host (404) and template (422), creates/reuses the
   managed deployment, and returns `202` with a durable operation id
   (status `QUEUED`). Duplicate clicks return the same in-flight operation
   (`deduplicated: true`).
3. Agent (next poll cycle, ≤ interval) claims the command via
   `POST /agents/commands/poll` (authenticated; atomic QUEUED→RUNNING).
4. Agent validates template/name/image **before touching Docker**, pulls
   `nginx:1.27-alpine`, runs it detached with the labels above.
5. Agent verifies: `docker ps --filter name=^<name>$` must show the
   container running; then probes `http://127.0.0.1:8080/` (result recorded
   as `http_ok`, non-fatal).
6. Agent posts the outcome to `POST /agents/commands/{id}/result`
   (authenticated; first-write-wins).
7. Backend persists status + evidence; dashboard polls
   `GET /operations/{id}` and the applications inventory, then shows the
   outcome and the application URL (`http://localhost:8080/`).

Start/Stop follow the identical path with `op_type` START/STOP; the agent
verifies `Up`/`Exited` state after each.

## 4. Operation states

| State | Meaning | Set by |
| --- | --- | --- |
| QUEUED | Durable record created; awaiting agent claim | Backend |
| RUNNING | Claimed by an agent; execution in progress | Backend (atomic claim) |
| SUCCEEDED | Agent verified the effect (`container_state` from `docker ps`, `http_ok` probe) | Agent evidence, validated by backend |
| FAILED | Agent-determined failure with sanitized `error_code`/`error_message` (`DOCKER_UNAVAILABLE`, `DOCKER_FAILURE`, `PORT_CONFLICT`, `UNAPPROVED_OPERATION`) | Agent, validated by backend |
| UNKNOWN | Outcome could not be determined (`TIMEOUT`, `VERIFY_FAILED`) | Agent |

An HTTP 200 from the agent is never treated as proof of a running
container: SUCCEEDED is stored only with evidence fields.

## 5. Local setup

See docs/DEVELOPMENT.md. Short: backend on :8000, frontend on :5173,
agent with `NIMBUSOPS_AGENT_SERVER_URL` + matching enrollment token;
Docker required only on the agent host for deployment features.

## 6. API contracts

Documented in docs/API.md (§Applications & deployments, §Agent command
endpoints). Phase 1 endpoints unchanged; all Phase 2 additions are
additive. Error contract `{"error": {"code", "message"}}` preserved and
extended (`DEPLOYMENT_NOT_FOUND`, `OPERATION_NOT_FOUND`, `INVALID_TEMPLATE`,
`INVALID_OPERATION`).

## 7. Test evidence (exact commands and results)

All commands run from the repository root, 2026-11-08, `.venv` Python
3.13.7:

| Suite | Command | Result |
| --- | --- | --- |
| Phase 2 backend | `.venv\Scripts\python -m pytest backend/tests/test_deployments.py -q` | **18 passed** |
| Phase 2 agent Docker (MOCKED) | `.venv\Scripts\python -m pytest agent/tests/test_docker_exec.py -q` | **15 passed** |
| Phase 2 agent worker (MOCKED HTTP+Docker) | `.venv\Scripts\python -m pytest agent/tests/test_worker.py -q` | **10 passed** |
| Phase 2 integration backend↔agent (MOCKED Docker only) | `.venv\Scripts\python -m pytest backend/tests_integration/test_phase2_flow.py -q` | **5 passed** |
| Full Python suite (Phase 1 + Phase 2) | `.venv\Scripts\python -m pytest --tb=no -q` | **93 passed, 3 warnings in 23.07s** |
| Full frontend suite | `cd frontend; npx.cmd vitest run` | **27 passed** (19 Phase 1 + 8 Phase 2) |
| Frontend build (tsc + vite) | `cd frontend; npm.cmd run build` | **clean, 43 modules** |
| Phase 1 integration regression | `.venv\Scripts\python -m pytest backend/tests_integration -q` | **2 passed** |

Coverage of the brief §11 test matrix:

- Backend: template validation ✓, deployment creation ✓, duplicate
  requests ✓ (same op returned), invalid host ✓ (404), unauthorized
  mutation (pinned documented trusted-local behavior; agent endpoints all
  401-guarded ✓), operation transitions ✓ (QUEUED→RUNNING→FAILED with
  error fields), operation persistence ✓ (read-back), agent result
  validation ✓ (bad status 422, wrong host 403, duplicate accepted=false).
- Agent (MOCKED Docker): Docker unavailable ✓ (typed
  `DOCKER_UNAVAILABLE` outcome), approved template execution ✓ (argv
  asserted: labels, no privileged, no mounts), invalid command rejection ✓
  (template/op type/name), duplicate command delivery ✓ (in-process dedup
  + backend first-write-wins), Docker failure ✓ (`DOCKER_FAILURE`),
  timeout ✓ (`UNKNOWN`/`TIMEOUT`), managed-resource isolation ✓
  (non-`nimbusops-` names raise `ManagedResourceError`).
- Frontend: template selection ✓, deploy interaction ✓, operation feedback
  ✓ (queued/running/succeeded/failed/unknown testids), start/stop controls
  ✓ (disabled states per real container state), loading/error states ✓.
- Integration: frontend→backend→agent→Docker — implemented; verified with
  MOCKED Docker (real frontend-exercised API path tested via API calls;
  browser path manually exercised in Phase 1 pattern but not re-run here),
  operation result→backend→frontend ✓, container state reconciliation ✓
  (honest NOT_REPORTED/RUNNING/EXITED), host disconnect during operation ✓
  (stays RUNNING, no re-claim, no duplicate execution), retry/duplicate
  delivery ✓ (bounded retries verified).

## 8. Real Docker verification — BLOCKED

Status: **BLOCKED** — no Docker Engine on this machine; installing Docker
or altering virtualization settings requires authorization the brief
withholds. Evidence of absence: `docker --version` → command not found;
`C:\Program Files\Docker\Docker` does not exist; no Docker Windows
service; `wsl -l -v` → WSL not installed.

What must be run on a Docker-capable machine (all commands ready):

```bash
# 1. Control server + agent (docs/DEVELOPMENT.md), then from the dashboard:
#    Applications -> select host -> nginx-demo -> Deploy
# 2. Verify for real (separate shells):
docker ps --filter label=nimbusops.managed=true          # container Up
curl -i http://localhost:8080/                            # HTTP/1.1 200
# 3. Stop via dashboard; verify:
curl -i http://localhost:8080/                            # connection refused
docker ps -a --filter label=nimbusops.managed=true        # Exited
# 4. Start via dashboard; verify HTTP 200 again.
# 5. Unrelated-container safety: record `docker ps -a` before/after the
#    whole exercise and diff — unrelated entries must be identical.
```

## 9. Failure recovery (operator runbook)

- `DOCKER_UNAVAILABLE`: start Docker Desktop / start the daemon on the
  host; operations may then be re-requested (safe: idempotent).
- `PORT_CONFLICT`: free host port 8080 (another process bound it), then
  Deploy again.
- `DOCKER_FAILURE`: read `error_message` (first 300 chars of docker
  stderr, sanitized); fix the host-level cause; re-request.
- `UNKNOWN` (`TIMEOUT`/`VERIFY_FAILED`): check the host with
  `docker ps -a --filter name=nimbusops-`; the container may actually be
  running or not — the dashboard never guesses. Then Stop (if running) or
  Start (if stopped) to converge, or re-Deploy.
- Stuck RUNNING (agent claimed, died): the operation remains RUNNING
  (honest); re-requesting the same action returns a NEW operation after
  the old one is terminal, or the same op while in flight — converge via
  Start/Stop after inspecting the host. Claim-timeout auto-reconciliation
  is deferred (Phase 3 per PRD).
- Agent offline: operations queue (QUEUED) and are claimed on reconnect
  within one poll interval.

## 10. Known limitations

1. Real-Docker verification BLOCKED (machine has no Docker; nothing was
   installed). All Docker behavior is verified against a mocked runner.
2. Application mutating endpoints are unauthenticated (trusted-local
   model, documented in docs/SECURITY.md; PRD RBAC is Phase 5).
3. Operations claimed by a dead agent stay RUNNING (no automatic claim
   timeout yet; documented recovery via re-request).
4. One deployment per (host, template); no multi-template concurrency per
   host beyond the nginx-demo catalog entry; no port allocation beyond the
   fixed 8080.
5. `app_url` assumes operator reachability from `localhost:8080` (single
   machine MVP); a remote host would need its address (Phase 3).
6. `docker pull` is invoked without digest pinning; the tag is pinned
   (`1.27-alpine`) and allowlisted, but a registry compromise could in
   theory mutate the tag. Digest pinning is future hardening.
7. Command history (FR-08 Should) is partially covered:
   `operation_events` persists an append-only log, but there is no
   dashboard view or API listing past operations yet (per-operation reads
   only).
