# Non-infrastructure acceptance ledger

Authority: user request “RESUME NON-INFRASTRUCTURE ACCEPTANCE”.
Baseline: `8203d461fb8edd93e79351a7fe129832f5a726f1`; isolated detached worktree.

## Checklist

- [ ] Audit tracked and untracked candidate diff, secrets, provenance and ownership.
- [ ] Verify and freeze focused implementation commits.
- [ ] Rebuild immutable release; synchronize version/hash; verify contents.
- [ ] Run final candidate Python/frontend/build/scoped static checks.
- [ ] Exercise independent-process worker/confirmation concurrency.
- [ ] Assess all eight npm audit package findings without forced upgrades.
- [ ] Rehearse migrations on synthetic disposable SQLite; preserve identities/data.
- [ ] Fresh-context whole-candidate review and final partial acceptance report.

## Boundaries and rulings

- No remote access, live database access, VM changes, deployment, merge or push.
- Real-VM acceptance and verified Katrina-copy migration remain BLOCKED only.
- Ruling: use this acceptance ledger rather than replay the completed implementation
  plan. Existing implementation tests are verification, not a request to rebuild
  features. New tests add acceptance coverage only.
- Ruling: freeze source first, build from that commit, then commit release pins and
  evidence separately. The final SHA includes pins; provenance names source SHA,
  avoiding a circular artifact/commit hash dependency.
- Initial audit found encoding-only BOM/mojibake in schemas alongside the intended
  UTC fix; normalize those accidental text changes before freezing.
- `ruff-results.json` is an existing scratch report and will not be committed or
  deleted. Existing historical plans/evidence are preserved.

## Evidence

- Current npm audit: 8 affected packages (5 moderate, 1 high, 2 critical); registry
  reachable. Detailed reachability assessment pending.
- Fresh baseline verification: 484 Python passed, 1 skipped; 148 frontend passed;
  TypeScript/Vite build passed. New local acceptance + migration suite: 7 passed.
- Four independent spawned processes contended for one job: exactly one admission;
  separate-process lock exclusion/reacquisition passed. Windows evidence only.
- Synthetic online backup migration twice: integrity/FK checks and byte-for-byte
  host/credential-version/telemetry preservation passed. Not Katrina evidence.
- Gitleaks redacted directory scan of all candidate files (excluding scratch)
  found no secrets. All inspected candidate file owners are the current Windows
  user; ACLs grant only user, SYSTEM and Administrators, no broad writable ACE.
- Nine freshly downloaded pinned Linux wheels match the baseline archive bytes.
- Scoped mypy strict (silent imports): 4 modules pass; Black: 6 files pass.
  Ruff: 9 B008 FastAPI Depends-default findings; gate is not clean.
- Fresh-context review: three Important unresolved findings, one deferred Minor;
  see `docs/DUAL_MODE_REVIEW_FINDINGS.md`. No product behavior changed.
- Ruling: freeze only a documented NO-GO local snapshot, not a clean acceptance
  sign-off. Important findings remain blockers; preserving implementation and
  avoiding new behavior follows the acceptance-only request. Cost if deferred:
  recovery/ownership/multi-target defects remain until focused remediation.
