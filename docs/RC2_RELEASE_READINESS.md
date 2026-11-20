# RC2 Release Readiness

- Candidate: `rc2/hardening` @ `b3fb6a7` + this documentation commit
- Baseline: `v1.0.0-rc1` = `965be27b7e98fa7470c44a5f37864fd58798b3ce`
- RC1 tag and branch untouched; no push, merge, tag, or publication performed
- Date: 2026-11-15

## Evidence actually collected in this window

| Check | Command | Result |
|---|---|---|
| Backend + agent + integration | `python -m pytest -q` | **264 passed, 1 skipped**, 3 warnings, 43 s |
| Frontend unit/UI | `npm test` (vitest) | **52 passed**, 12 files |
| Type check | `npx tsc -b` | exit 0 |
| Production build | `npx vite build` | exit 0; JS 215.23 kB, CSS 17.59 kB |
| Agent wheel | `pip wheel --no-deps ./agent` | `nimbusops_agent-1.0.0rc2-py3-none-any.whl`, contains `__main__.py` + console script |
| Windows identity ACL | `save_identity` + `icacls` | single ACE for current user, inheritance removed |
| Dependency audit | `npm audit` | 8 advisories (5 moderate, 1 high, 2 critical) — dev tooling except `react-router-dom` |
| Docker runtime | `docker --version` | CLI not found |
| WSL | `wsl -l -v` | no distributions installed |

The one skipped test is POSIX-permission-only
(`test_save_identity_file_is_mode_0600`); the Windows ACL path was exercised
directly.

## 14-gate matrix

A gate is PASS only when its own acceptance evidence exists. Local unit tests
alone do not close a runtime, isolation, or incident gate.

| Gate | Verdict | Basis |
|---|---|---|
| G1 Functional completeness | **PARTIAL** | F01/F02/F04/F07/F08/F10/F12/F14/F15 closed; F03 partial; F11/F13 open; enrollment and operation surfaces work in tests |
| G2 Backend stability | **PARTIAL** | Concurrency/transaction defects closed with CAS + DB constraint; no sustained-load or latency measurement |
| G3 Agent reliability | **PARTIAL** | Tokenless restart and atomic identity closed; claim fencing prevents stale wins; crash-window result replay (F03) not implemented |
| G4 Multi-host integration | **BLOCKED** | No RC2 two-host enrollment/operation run; production hosts not used |
| G5 Docker runtime validation | **BLOCKED** | No isolated Docker Engine; mocked-CLI tests are not runtime acceptance |
| G6 Authentication/authorization | **PARTIAL** | F01/F04/F08 closed; all mutation paths still operator-gated; no independent security review |
| G7 Secret handling | **BLOCKED** | F14 closed; historical incident closure requires the owner's exposure/reuse determination |
| G8 TLS/network isolation | **UNVERIFIED** | No ingress/TLS/firewall/ACL demonstration |
| G9 Deployment reproducibility | **PARTIAL** | Real entrypoint, package metadata, wheel build, corrected runbook; clean-host install not executed |
| G10 Observability | **PARTIAL** | Health/readiness now dependency-honest; alerting and log rotation not verified |
| G11 Recovery/rollback | **PARTIAL** | Requeue + fencing tested; documented restore/rollback drill not executed |
| G12 Documentation | **PARTIAL** | RC2 decisions, matrix, security, runtime, soak, readiness and verdict written; runbook corrected; older docs retain historical context |
| G13 Reliability soak | **BLOCKED** | No ≥60-minute two-host soak for RC2 |
| G14 CI/regression coverage | **PARTIAL** | Full local suites, type check and build pass; no CI run on this branch, nothing pushed |

Totals: **0 PASS, 9 PARTIAL, 4 BLOCKED, 1 UNVERIFIED** (14 gates).

## Artifacts

| Commit | Scope |
|---|---|
| `8a48256` | RC1 recovery fix cherry-picked (F02) |
| `28936fd` | Enrollment contract + legacy re-enrollment hardening (F01/F08) |
| `f9dd635` | Agent enrollment, atomic identity, Docker fail-closed behavior (F01/F04/F05/F06/F14/F07 echo) |
| `3323d64` | Dispatch gating, result fencing, dedup, history paging (F04/F07/F10) |
| `2f86f83` | Health/readiness, build identity, UI/status reconciliation (F10/F12/F15) |
| `b3fb6a7` | Agent packaging + runbook + module entrypoint (F09) |

## Blocking findings for release

1. **G5** — Docker ownership/disablement/verify behavior has no real-Engine
   acceptance.
2. **G13** — no sustained two-host evidence; RC1's soak failure is not
   superseded.
3. **G4** — no RC2 multi-host secure-enrollment + operation run.
4. **G7** — historical credential exposure/reuse is unresolved by the owner.
5. **G8** — ingress isolation unverified.

## Non-blocking but open

- F03 crash-window result replay.
- F11 fleet N+1 / unpaginated legacy list.
- F13 localhost application links.
- Dev-tool dependency advisories and the `react-router-dom` 6→7 upgrade
  (`RC2_SECURITY_ACCEPTANCE.md`).

## Readiness statement

RC2 is a materially safer candidate than RC1: the enrollment trust root is
unambiguous, a shared secret cannot move another host's identity, disabled
Docker hosts cannot be mutated even with queued work, mutations require proven
ownership, unverifiable state is reported as UNKNOWN, concurrent operations and
results have database-enforced single winners, and history/health tell the
truth.

It is **not release-ready**. Four gates are blocked and one is unverified, and
none of them can be closed by more local unit tests.
