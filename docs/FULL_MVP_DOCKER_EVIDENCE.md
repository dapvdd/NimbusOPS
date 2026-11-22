# Full MVP M3/M4: local Docker contract evidence

## Verdict and scope

Local contract validation passed: **125 tests, 3 dependency deprecation warnings,
0 failures**, final run **38.98 seconds**, exit **0**. This is **not Docker Engine
acceptance**, Linux acceptance, or full MVP sign-off. Docker CLI is absent:
`Get-Command docker -ErrorAction SilentlyContinue` returned null. No Engine
commands, installations, remote hosts, privileged services, or historical state
were used.

Evidence collected on Windows with Python **3.13.7**. Observed repository HEAD at
the end of validation: `123d41c6f863f1d6d860adeac2375fa090ca67c5`.
This was a shared integration worktree with coordinator-owned uncommitted agent
journal changes; results describe the tested working tree, not a clean commit.
Only this document and `backend/tests_integration/test_full_mvp_recovery.py` were
created by this validation task. No commits were made.

## Exact reproduction

Run from the repository root with existing Python dependencies:

```powershell
python -m pytest agent/tests/test_docker_exec.py agent/tests/test_inventory_and_restart.py agent/tests/test_inventory_heartbeat.py agent/tests/test_worker.py agent/tests/test_result_recovery.py agent/tests/test_authorization_fail_closed.py agent/tests/test_resource_isolation.py agent/tests/test_rc2_docker_safety.py backend/tests/test_docker_authz.py backend/tests/test_deployments.py backend/tests/test_recovery.py backend/tests/test_restart_op.py backend/tests/test_inventory_api.py backend/tests/test_rc2_docker_safety.py backend/tests/test_agent_contract_compat.py backend/tests_integration/test_phase2_flow.py backend/tests_integration/test_full_mvp_recovery.py -q
```

Results:

| Check | Actual result |
| --- | --- |
| Existing selected suite, before adding recovery integration | 123 passed, 3 warnings, 38.17 s, exit 0 |
| New recovery test initial standalone execution | 2 passed, 3 warnings, 6.89 s, exit 0 |
| Final selected suite, including final new test implementation | 125 passed, 3 warnings, 38.98 s, exit 0 |
| `python -m ruff check backend/tests_integration/test_full_mvp_recovery.py --output-format concise` | All checks passed, exit 0 |
| `python -m black --check backend/tests_integration/test_full_mvp_recovery.py` | 1 file unchanged, exit 0 |
| `python -m mypy --strict --follow-imports=silent backend/tests_integration/test_full_mvp_recovery.py` | No issues in 1 source file, exit 0 |

Warnings concern Starlette's AnyIO BlockingPortal alias and deprecated
`websockets.legacy` / `WebSocketServerProtocol`; none were test failures.
Initial static checks found fixture import/style issues and untyped reuse of an
existing fake executor. These were corrected only in the new test; final static
checks above passed. Mypy checks this test, not the full repository.

## What the evidence establishes

- Existing agent tests exercise Docker argv construction, managed ownership and
  safety guards, inventory/restart behavior, resource limits, worker dispatch,
  explicit authorization/fail-closed behavior, durable pending outcomes, and
  corrupt/unreadable journal rejection. Docker subprocess responses are test
  doubles, not Engine observations.
- Existing backend tests exercise Docker authorization, deployment lifecycle,
  recovery/reconciliation, restart operations, inventory, safety and agent wire
  compatibility against disposable SQLite fixtures.
- Existing Phase 2 integration exercises real uvicorn on loopback, real HTTP,
  real Sender/CommandWorker, operator login and backend persistence, including
  deploy/stop/start, duplicate requests, disconnect and failure reporting.
  Its Docker executor is mocked.
- The new parametrized integration test closes a narrower recovery boundary gap:
  a real worker writes a `FileOutcomeStore` journal after one synthetic Docker
  dispatch; three submissions lose either the request (no backend delivery) or
  acknowledgement (real backend accepted the result). A **new Sender, worker,
  executor and file-store instance** then recovers the outcome over real HTTP.
  Assertions verify the pending file, generation 1, RUNNING versus SUCCEEDED
  before recovery, successful terminal evidence, unchanged completion timestamp
  for lost acknowledgements, empty journal, zero second-executor calls, idle
  subsequent polling, and exactly one matching inventory deployment.

The new test reuses the established integration fixture's disposable SQLite DB
and loopback server at `127.0.0.1:8992`; it uses pytest `tmp_path` for its journal.
It performs no real Docker execution or real application HTTP probe. The
synthetic executor supplies `container_state=RUNNING` and `http_ok=true`; these
values prove result propagation only. Run this fixture serially because the
existing integration fixture uses a fixed port.

## Remaining gaps and boundaries

- Object-graph restart is tested, **not** OS process termination, machine reboot,
  service manager recovery, power-loss durability, or backend process restart in
  the new integration test. Existing backend recovery tests separately cover
  timeout requeue and persistence across fresh app instances.
- Existing unit tests cover pending-result reconciliation with a newer claim
  generation; the added real-HTTP test does not force lease expiry/reclaim.
- No live image pull, container create/start/stop/restart, inspect, real resource
  isolation, managed-versus-unmanaged Engine behavior, endpoint reachability or
  Linux owner-only journal permission enforcement was validated here.
- This is best-effort outcome recovery, **not exactly-once Docker execution**.
  A crash after a Docker side effect but before journal persistence remains a
  known gap; the journal cannot reconstruct an outcome that was never written.
- No critical contract failure was observed in the executed tests. This does
  not establish the absence of defects outside those cases.

## Minimum authorization for fresh-host Docker acceptance

Before live validation, obtain explicit authorization naming:

1. One **fresh disposable Linux host/VM**, its identity and access method,
   with no production/historical workloads or credentials. Prefer Docker Engine
   already installed and healthy; installation/package changes require separate
   explicit approval and are not included in this request.
2. Permission to use that host's Docker API/socket for the scoped test account
   (Docker access is effectively privileged), and permission to run the NimbusOps
   agent in Docker-enabled mode with a disposable backend DB and fresh scoped
   enrollment/operator credentials.
3. Permission for outbound registry access and the allowlisted image pull
   `nginx:1.27-alpine`, creating only test-owned managed containers, binding the
   configured test application port **18080**, and making HTTP probes from the
   agreed local/network vantage point. Agree firewall changes separately.
4. Permission for controlled deploy/stop/start/restart, agent process stop/start,
   induced result-transport interruption and timeout recovery, and inspection
   of container labels/resource settings and journal permissions. Backend restart
   or host reboot requires explicitly including those disruptions.
5. A bounded cleanup plan limited to newly created test containers, disposable
   agent/backend state and test credentials; no broad prune, deletion of existing
   images/volumes, host configuration reset, or unrelated service mutation.

Record Docker client/server versions, host OS, exact tested revision, real
container IDs/labels, inspect resource settings, command/result evidence,
application HTTP responses, interrupted-delivery/restart recovery and cleanup
results. Until that authorized run occurs, M3/M4 live Docker acceptance remains
**blocked / unverified**, regardless of the passing synthetic contract suite.
