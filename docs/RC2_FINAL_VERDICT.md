# RC2 Final Verdict

- Candidate: `rc2/hardening` @ `b3fb6a7` (+ documentation commit)
- Baseline: `v1.0.0-rc1` = `965be27b7e98fa7470c44a5f37864fd58798b3ce`
- Date: 2026-11-15

## Verdict: NOT GO — RC2 is not release-ready

This is a truthful, evidence-bounded verdict. RC2 closes the RC1 code-level
security, correctness, and reliability defects that could be closed locally, but
it cannot satisfy the release gates that require an isolated Docker Engine, a
two-host soak, and an incident-owner decision.

| Dimension | Result |
|---|---|
| Defects closed | 11 of 15 (F01, F02, F04, F05, F06, F07, F08, F09\*, F10, F12, F14, F15) — F09 is partial in scope, F03 partial, F11/F13 open |
| Regression coverage | 264 backend/agent/integration tests passed, 1 POSIX-only skipped; 52 frontend tests passed; `tsc -b` and `vite build` clean |
| Security controls | Code-level controls pass internal acceptance; runtime proof and historical incident closure missing |
| Release gates | 0 PASS · 9 PARTIAL · 4 BLOCKED · 1 UNVERIFIED |

\* F09: entrypoint, packaging, and runbook are fixed and the wheel builds; a
clean-host installation was not executed.

## Why it is not GO

1. **No real Docker Engine (G5, blocked).** Ownership verification, disablement
   at execution, and honest STOP verification are proven only against a fake
   Docker CLI. The environment has no `docker` CLI and no WSL distribution.
2. **No two-host soak (G13, blocked).** RC1's failed 171/171 soak is not
   superseded. No ≥60-minute RC2 run exists.
3. **No RC2 multi-host integration run (G4, blocked).** Two independent hosts
   were not enrolled and operated end-to-end on this candidate.
4. **Incident closure unresolved (G7, blocked).** Whether historically exposed
   credential material was valid for or reused against a live system is an
   owner decision; RC2 hardened the mechanism but cannot close the history.
5. **Ingress isolation unverified (G8).** TLS, firewall, and ACLs were not
   demonstrated.

Additional open (non-blocking) items: F03 crash-window result replay, F11 fleet
N+1 list, F13 localhost application links, and dev-tool dependency advisories.

## What would make RC2 GO

In order:

1. Authorize one **isolated, disposable Docker host** (never DavidLab/SPECTRA/
   MAMMON/DCC) and run `RC2_DOCKER_RUNTIME_ACCEPTANCE.md` R1–R12.
2. Authorize **two disposable Docker-capable hosts** and a 60+ minute window;
   run the pre-declared soak in `RC2_MULTIHOST_SOAK_REPORT.md`.
3. Obtain the **incident owner's** determination and evidence that exposed
   credentials are revoked/rotated.
4. Demonstrate the intended **ingress policy** (TLS termination, bind address,
   firewall/ACL) on the target deployment.
5. Plan the **dependency upgrade** (react-router 7, vite 8, vitest 5) as its own
   verified change, or record a formal risk acceptance.
6. Re-run all 14 gates on the resulting immutable commit and re-issue this
   verdict. Only then may a push, merge, tag, or publication be considered.

## Next release decision (exact)

**Request:** authorize an isolated Docker Engine and two disposable Docker hosts
with a ≥60-minute window, plus an incident-owner statement on historical
credential exposure. Without (1) and (2) there is no path to a GO verdict,
regardless of further local code changes.

## Preserved and untouched

- `v1.0.0-rc1` tag and its commit; no rewrite.
- RC1 run-6/run-7 harness evidence in `.worktrees/rc1-validation`.
- DavidLab production, SPECTRA, MAMMON, DCC, and the existing demo container.
- No push, merge, tag, or publication was performed.
- No secrets, databases, runtime identities, or raw sensitive logs were
  committed.
