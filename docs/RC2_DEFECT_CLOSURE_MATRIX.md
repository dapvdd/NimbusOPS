# RC2 Defect Closure Matrix

- Candidate: `rc2/hardening` @ `b3fb6a7`
- Method: TDD per workstream — regression test written first and observed RED,
  then the minimal fix, then focused suites, then the full suite.
- Evidence classes:
  - **runtime** — exercised in this environment with real OS filesystem/DB.
  - **mocked-runtime** — agent/Docker boundary tested with a fake Docker CLI
    (no Engine; see `RC2_DOCKER_RUNTIME_ACCEPTANCE.md`).
  - **static** — code/packaging inspected or built, not executed end-to-end.

Status legend: CLOSED = defect fixed with regression coverage; PARTIAL =
primary failure mode fixed, named residual work remains; OPEN = deferred.

| ID | Severity | Status | What changed | Regression evidence | Class |
|---|---|---|---|---|---|
| F01 | P1 | **CLOSED** | One credential per enrollment; explicit `enrollment_mode`; agent sends `bootstrap_token` via file/env; conflicting credentials → 400 `ENROLLMENT_MODE_CONFLICT` | `backend/tests/test_rc2_enrollment_contract.py` (5), `agent/tests/test_client.py`, `test_config.py`, `test_main.py` bootstrap cases | mocked-runtime + runtime DB |
| F02 | P1 | **CLOSED** | `1e5709f` recovery integrated as `8a48256`: tokenless restart allowed when an identity exists, config construction inside the try/except, exit code 2 | `agent/tests/test_main.py::test_main_accepts_tokenless_restart_with_stored_identity`, `::test_main_returns_exit2_on_config_error`, `test_config.py` identity cases | runtime |
| F03 | P1 | **PARTIAL** | Claim fencing (`claim_generation`) and single-winner result CAS stop stale/duplicate wins and requeue-after-delay corruption. Durable execution receipt + result replay after a process crash is **not** implemented | `backend/tests/test_rc2_transactions.py` (stale fence, one winner), `agent/tests/test_worker.py` claim echo | mocked-runtime |
| F04 | P1 | **CLOSED** | Disabled host claims no op of any type (queued work preserved); agent refuses execution and reports `UNKNOWN`/`DOCKER_DISABLED`; heartbeat flag consumed | `backend/tests/test_rc2_docker_safety.py`, `agent/tests/test_worker.py`, `agent/tests/test_client.py` | mocked-runtime |
| F05 | P1 | **CLOSED** | Ownership requires `nimbusops.managed=true` + exact `nimbusops.deployment`; deploy refuses unmanaged collisions and owned recreation | `agent/tests/test_rc2_docker_safety.py` (13) | mocked-runtime (Engine still required) |
| F06 | P2 | **CLOSED** | Inspection failure/empty output → `UNKNOWN`/`VERIFY_FAILED`; paused parsed as PAUSED; state and HTTP health separate | `agent/tests/test_rc2_docker_safety.py` F06 cases | mocked-runtime |
| F07 | P2 | **CLOSED** | Partial unique in-flight index, duplicate-safe creation, CAS results, shared enrollment transaction, migration column + index | `backend/tests/test_rc2_transactions.py` (4), `test_operation_history.py` | runtime (SQLite) |
| F08 | P1 | **CLOSED** | Shared secret can never replace an existing credential; operator bootstrap is the only re-enrollment path (stable host id) | `test_rc2_enrollment_contract.py::test_legacy_reenroll_does_not_replace_existing_credential`, `::test_bootstrap_reenroll_rotates_with_stable_identity`; old unsafe pin rewritten | runtime DB |
| F09 | P2 | **PARTIAL** | Real `__main__`, `agent/pyproject.toml`, console script, wheel builds; runbook rewritten to actual env/CLI. Clean-host install not executed | `agent/tests/test_main.py::test_python_m_nimbusops_agent_runs_main`; `pip wheel` produced `nimbusops_agent-1.0.0rc2-py3-none-any.whl` with `__main__.py` + entry point | runtime build + static |
| F10 | P2 | **CLOSED** | Newest-first, server-side status filter, offset window, pre-window `total`; UI pages with "Load older" | `backend/tests/test_operation_history.py` (rewritten to new contract), `frontend/.../activity.paging.test.tsx` | runtime |
| F11 | P2 | **OPEN** | Deferred: fleet list still N+1 for latest metrics and the frontend uses the legacy unpaginated route | none yet | — |
| F12 | P2 | **CLOSED** | Degraded dependency reported as `status=degraded`; `/ready` returns 503; UI shows degraded, not online | `backend/tests/test_rc2_health.py` (6), `frontend/.../appshell.health.test.tsx` | runtime |
| F13 | P2 | **OPEN** | Deferred: `app_url` still targets `http://localhost:<port>/` (products decision on host-specific endpoints) | none yet | — |
| F14 | P2 | **CLOSED** | Atomic identity write: unique temp file in target dir, restricted before writing, fsync, `os.replace`; failed replace keeps old file and removes temp; POSIX 0600, explicit Windows ACL | `agent/tests/test_config.py` (atomicity/leftover/mode tests); Windows runtime check: `icacls` shows a single ACE `DESKTOP-36UEJS7\user:(F)` (inheritance removed) | runtime |
| F15 | P3 | **CLOSED** | Single authoritative status: real `VERSION` + `build` in health, "Phase 3A"/"NOT IMPLEMENTED" claims removed, README points at the verdict, RC2 status stated once | `backend/tests/test_rc2_health.py` version/build tests, `appshell.health.test.tsx` | runtime |

## Test-count trail (for audit)

| Stage | Command | Result |
|---|---|---|
| RC1 baseline | full pytest | 217 passed |
| After F01/F08 backend | focused | 26 passed |
| After F01/F02/F14 agent | agent suite | 70 passed |
| After F04/F05/F06 agent | agent suite | 87 passed, 1 skipped |
| RC2 candidate | full pytest (`backend/tests`, `agent/tests`, `backend/tests_integration`) | **264 passed, 1 skipped**, 3 warnings, ~43 s |
| RC2 candidate | `npm test` (vitest) | **52 passed**, 12 files |
| RC2 candidate | `tsc -b` / `vite build` | exit 0 / built (`index-*.js` 215.23 kB, CSS 17.59 kB) |

The single skipped test is `test_save_identity_file_is_mode_0600`, skipped on
Windows by design; the Windows ACL path is covered by the `icacls` runtime
check above.

## Residual risk summary

- F05/F06 are proven only against a fake Docker CLI here. They require the
  isolated-Engine pass in `RC2_DOCKER_RUNTIME_ACCEPTANCE.md` before they can be
  called runtime-accepted.
- F03's crash-window (effect applied, result never delivered) remains: work will
  be re-delivered after timeout, and a non-idempotent restart could repeat an
  effect. Fencing prevents *wrong* state, not repeated effect.
- F11/F13 are known product-scale/UX gaps; neither is a security regression.
