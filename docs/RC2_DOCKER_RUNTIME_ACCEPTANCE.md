# RC2 Docker Runtime Acceptance

**Verdict: BLOCKED — not executed.**

Mocked-Docker unit tests are not runtime acceptance. No isolated Docker Engine
was available in this environment, and using the protected DavidLab production
host or a mock as a substitute is explicitly out of scope.

## Environment evidence (2026-11-15)

| Probe | Result |
|---|---|
| `docker --version` | `docker CLI: NOT FOUND` |
| `wsl -l -v` | "Windows Subsystem for Linux has no installed distributions." |
| Host platform | Windows (`win32`), Python 3.13.7, Node v24.15.0 |
| Protected systems | DavidLab production, SPECTRA, MAMMON, DCC and the existing demo container were **not** touched |

Because neither the Docker CLI nor a WSL distribution exists, there is no local
Engine to create containers in. Installing Docker/WSL requires authorization
that was not granted, so the gate stays open.

## What is already covered without an Engine

These are necessary but **not sufficient** for runtime acceptance:

- constrained argv construction (no shell, no interpolation) —
  `agent/tests/test_docker_exec.py`, `test_inventory_and_restart.py`
- label ownership proof, unmanaged-collision refusal, owned-recreation refusal —
  `agent/tests/test_rc2_docker_safety.py`
- honest `UNKNOWN`/`VERIFY_FAILED` on inspection failure, PAUSED parsing —
  same file
- disablement refusal at execution — `agent/tests/test_worker.py`
- backend dispatch gating and queue preservation —
  `backend/tests/test_rc2_docker_safety.py`

## Required execution (when an isolated Engine is authorized)

Preconditions:
1. A disposable host/VM with a local Docker Engine that is **not** any
   production host. Record `docker version`, kernel, and Engine version.
2. Operator authorization to create/remove containers on that host only.
3. A fresh control-server DB (SQLite or Postgres) and one enrolled agent.
4. Record the candidate commit (`b3fb6a7` or later) with
   `NIMBUSOPS_BUILD_SHA` set to that commit.

Procedure and pass criteria:

| Step | Action | Pass criterion |
|---|---|---|
| R1 | Deploy `nginx-demo` to the host | Container starts; `/health` and `/ready` healthy; operation SUCCEEDED with `container_state=RUNNING` and `http_ok=true` |
| R2 | Inspect labels | `nimbusops.managed=true`, `nimbusops.deployment=<deployment id>` present |
| R3 | STOP | Container `Exited`; operation SUCCEEDED with `container_state=EXITED` |
| R4 | START then RESTART | Container `Up`; both SUCCEEDED with verified state |
| R5 | Redeliver the same result / submit a stale claim generation | `accepted=false`; stored evidence unchanged |
| R6 | Queue STOP, disable Docker, poll | No command delivered; operation remains QUEUED |
| R7 | Re-enable Docker and poll | Same queued operation delivered once |
| R8 | Create a same-named unmanaged container, attempt START | FAILED, no mutation, unmanaged container untouched |
| R9 | Attempt DEPLOY while the owned container exists | FAILED `CONTAINER_EXISTS`; no recreation |
| R10 | Make `docker ps` fail (stop the Engine mid-verify) | `UNKNOWN`/`VERIFY_FAILED`, never SUCCEEDED/EXITED |
| R11 | Kill the agent mid-operation; wait past `timeout_at` | Operation requeued and re-delivered; stale result fenced |
| R12 | Inspect agent identity file on the host | Mode 0600, no plaintext token in logs/argv |

R10–R12 may use controlled fault injection on the disposable host only.

## Unblock requirement

Provide an isolated Docker Engine (non-production) and authorization to run the
table above. Until then G5 is **BLOCKED** and RC2 cannot be released.
