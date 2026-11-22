# Full MVP release-candidate status

## Verdict: BLOCKED — local integration partially verified

This program implements and validates development changes; it does not convert
synthetic results into real-host acceptance. No main merge, push, deployment,
root installer, Docker Engine operation or historical acceptance mutation occurred.
Exact final test totals are recorded below when coordinator verification finishes.

## Repository reconciliation and baseline

Integration worktree: `C:/Users/user/.local/share/opencode/worktree/2bef8e/full-mvp-integration`.
Branch: `integration/full-mvp-rc`. Base: `7194f1009315249925d35c1738c05e1878e8e5f8`.
Fourteen worktrees were discovered. The dashboard branch contains the approved
finalization commits through7194f10; native worktree creation initially selected
main, then the new integration branch was explicitly created at7194f10.

| Source | Revision | Disposition |
| --- | --- | --- |
| main | adf459e9d851dfc7d6de0587d14f445524717919 | one missing ignore-rule commit integrated as307d9c2 |
| dashboard |7194f1009315249925d35c1738c05e1878e8e5f8| retained entire ancestry, no dashboard reimplementation |
| zero-touch hardening |41c9af144ad7cd1954f6bcf37dcad2f87dae5d2c| durable agent recovery/fail-closed Docker guards integrated as370826d; regression tests first in426664d |
| UTC normalization |c0255d4| implementation already present via b812976; not duplicated |
| real Docker branch |d571d69005760f3a8f91e1338d80406ee5425ec4| ancestor of dashboard baseline, not missing feature line |
| production Docker/private |98f15dd9f6a8aa9c8cd5f129e5f0bd451e4f30d3| divergent alternative packaging/deployment line; not blindly merged |
| monitoring private |e021a792b6f334bbbd2d4f45bac03683171252f7| ancestor of98f15dd, not a second missing chain |
| classroom intelligence |74a11a29d52166bee4622f939996ad7ef42d3fab| core cookie auth already shared; optional alerts/sparklines/Windows installer not imported into approved UI |

Production/private branches contain useful profile/installation machinery but a
competing agent installer contract. Their historical NO-GO reports are not live
acceptance evidence. Current candidate retains the reviewed dual-mode installer,
protected identity and custom verified CA path. Fresh deployment configuration
requires validation; a development branch is not a deployment recipe.

All original dirty/untracked files were left in their original worktrees, including
acceptance reports/harnesses in dual-mode-onboarding and multihost demo edits. They
were not staged/copied into this branch. The current tracked acceptance report is
older than the separate preserved outcome; it must not be mistaken for the latest
historical verdict.

## Historical Zero-Touch evidence — immutable

Candidate72a36e94b19fd39b555d7b2e477b325fe28de1c9; job
007ab9c1-9a05-4a43-9097-474b864e4d4b; acceptance FAIL, cleanup PASS, deployment NO-GO.
Persisted VERIFYING/INSTALL_ADMITTED, RECONCILIATION_REQUIRED, expired unconsumed
token, no installed agent/hosts/telemetry. Original dispatch discarded stdout and
stderr. Exact failure **UNKNOWN**, not proven to be SSH/sudo/token/systemd failure.
The newer local outcome report was read without opening its historical database,
remote host, root state or protected wrapper. No retry/rearm/snapshot restore.

## Milestone and evidence matrix

| Milestone | Development evidence | Mandatory remaining gate |
| --- | --- | --- |
| M0 | worktrees/ancestry reconciled, dedicated baseline, main hygiene + agent recovery integrated; baseline542 Python/226 frontend passed | no main merge/push requested |
| M1 | allowlisted bounded installer protocol, numeric exits, timeout/cancellation uncertainty, no redispatch regressions | new authorized real Ubuntu Zero-Touch; historical exact root cause unavailable |
| M2 | real local HTTP enrollment/telemetry; disposable status/replay/migration/backup tests | service identity/systemd/real-host telemetry/reconnect |
| M3 | Docker authorization/resource/isolation tests; real local HTTP pending-result recovery, synthetic executor | actual authorized Docker Engine lifecycle and inspect evidence |
| M4 | Chromium→Vite→FastAPI19/19; local HTTP interrupted result/ack recovery | integrated real-host onboarding+monitoring+Docker and service/network restart |
| M5 | immutable source-matched agent, local build/static/review and disposable backup validation | complete accepted real-host gates, validated target proxy/install config and release sign-off |

Evidence details: `FULL_MVP_ZERO_TOUCH_FINDINGS.md`,
`FULL_MVP_MONITORING_EVIDENCE.md`, `FULL_MVP_DOCKER_EVIDENCE.md`,
`FULL_MVP_SECURITY_GATES.md`. Operator startup/recovery and consolidated minimum
authorization: `FULL_MVP_OPERATOR_RUNBOOK.md`.

## Agent distribution and recovery

New immutable artifact:
`nimbusops-agent-1.0.0rc2-fullmvp1-ubuntu24.04-amd64.tar.gz`.
SHA256: `a522b93c4e90d5708eef6f663f7a2d4ecc22e566155349b93d8bd77a1ccfe6df`.
Backend/frontend pins agree; release regression compares every shipped source file.
Old dualmode1/2 bytes retained. Builder reuses existing wheel bytes, installs nothing.
This proves archive consistency, not fresh vulnerability scans or Ubuntu execution.

Pending result journal recovers interrupted delivery and claim generations without
repeating recorded effects. Corruption/unreadability fails closed. Crash between
Docker execution and journal write remains uncertain; exactly-once is not claimed.
Installer phases become durable after transport returns/handled interruption;
SIGKILL can lose phase evidence, but admission still forbids redispatch.

## Verification ledger

- Baseline: `python -m pytest -q`:542 passed,11 skipped,3 dependency warnings.
- Baseline frontend: `npm test -- --run`:226 passed/32 files; router future warnings.
- Agent post-repair:146 passed,1 skipped; outcome journal9/9.
- Monitoring selection:186 passed,10 skipped (POSIX CA permission cases).
- Docker/local HTTP recovery selection:125 passed,3 dependency warnings.
- Existing isolated browser harness:19 passed,0 failed; owned processes stopped,
  disposable DB removed. Artifacts: `C:/Users/user/AppData/Local/Temp/opencode/nimbusops-real-browser-f0m24baj`.
- Production `npm run build`: TypeScript/Vite PASS after final diagnostic UI edits.
- Final frontend suite: `npm test -- --run` → 228 passed/32 files (React Router future warnings).
- Final `npx tsc --noEmit`: PASS.
- Scoped strict mypy worker/docker executor/rebuild helper PASS; scoped Ruff PASS.
- Final full Python suite: `python -m pytest -q` → 600 passed, 11 skipped,
  3 dependency warnings, exit 0 in 135.14 s (includes real loopback agent/backend
  integration and the corrected diagnostics/regression tests).

## Remaining blockers

### P0 release gates
- No newly authorized successful real Ubuntu Zero-Touch acceptance.
- No real-host service/enrollment/heartbeat/telemetry and restart proof.
- No authorized actual Docker Engine lifecycle/isolation/reconciliation proof;
  Docker executable is absent in this Windows environment.

### P1 before staging acceptance/sign-off
- Final independent review and full regression closure must be recorded.
- Validate exact proxy TLS/certificate strategy and least-privilege executor
  profile on the fresh target; canonical Zero-Touch installer is telemetry-only.
- Run POSIX-only permission gates and privileged service lifecycle on new guest.
- Freeze SHA, approve one independent action identity, validate safe log capture,
  backup/restore, cleanup and rollback on fresh state.

### P2 limitations
- Repository-wide strict mypy debt predates this program; scoped checks do not
  establish a globally clean typing gate.
- Optional Sprint4B alerts/sparklines/Windows task installer/private deployment
  profile branch reconciliation is not included by implication in Full MVP.
- Existing browser scope does not prove real provisioning, real Docker, assistive
  technology certification or elapsed session TTL.

## Recommended release action

Keep this branch local. Complete any unresolved local findings, freeze its final
SHA, then approve the single consolidated fresh-infrastructure request in the
operator runbook. Only successful mandatory evidence may advance the verdict to
FULL_MVP_RC_READY; staging deployment itself remains a separate approval.
