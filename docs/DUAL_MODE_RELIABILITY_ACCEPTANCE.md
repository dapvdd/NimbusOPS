# Onboarding reliability sprint — local verification

Baseline: `f4c10150764ea78172ebfa37f2c35a12a2acedf2`.
Final revision: resolve the local commit containing this report with
`git log -1 --format=%H -- docs/DUAL_MODE_RELIABILITY_ACCEPTANCE.md`.

## Scope

Focused remediation of A/B/C; no database schema, enrollment protocol, agent,
installer, dependency or infrastructure change. Existing idempotency/ownership
tables are reused. No production access, push, merge, deployment or live restart.
Previous acceptance report is historical evidence for the baseline, not the new
revision. Katrina deployment and real-VM acceptance remain **NO-GO**.

## Implemented boundaries

- Actor-scoped stable confirmation keys map atomically to one job in
  `provisioning_requests`; payload changes under the same key conflict. A replay
  returns the original job even after expiry or target-policy removal, never
  dispatches it again. ADMIN plus original requester checks protect recovery,
  progress reads and retries.
- Browser stores confirmation intent before sending the approval, recovers by
  authenticated lookup on refresh, and explicitly resends only the same key if
  needed. Storage failure blocks initial dispatch. No credentials are stored.
- Local SQLite write fencing serializes ownership-sensitive issue/consume/
  confirmation paths. Automatic token authority is checked against the owning
  job and generation. Manual/legacy paths cannot bypass held reservations.
- Bootstrap consumption, host creation, consumed-by linkage, target mapping and
  ownership binding share one commit. Binding conflicts roll back the host/token
  transaction rather than stranding an identity or burning a token.
- Terminal jobs without reconciliation needs can clear their local reference to
  add another target. Missing/forbidden references stop polling and have an
  explicit local-only escape warning; clearing does not cancel/release ownership.
  Uncertain active jobs retain tracking and do not offer a blind reinstall.

## Verification ledger

Focused regression evidence is in `backend/tests/test_onboarding_reliability.py`
and `frontend/src/views/__tests__/automatic-setup.test.tsx`. Process cases use
spawned independent SQLite connections and cover confirmation duplicate races
and single token consumption in both modes; these are Windows tests, not Linux
flock/stress acceptance. Existing manual enrollment/auth/lifecycle regressions
remain part of the full suite.

Final full Python suite: **499 passed, 1 skipped, 3 dependency deprecation warnings**
(`python -m pytest -q`, Windows; POSIX permission skip). No new real-VM claims
follow from local tests. Focused provisioning API/jobs/reliability: **26 passed**.

Completed after review fixes: frontend **154 passed / 25 files**, TypeScript/Vite build
passed; targeted reliability backend now **12 passed**; migration/local acceptance
**7 passed**; scoped strict mypy (silent imports) passes 3 modified modules;
Gitleaks candidate scan found no secrets. Full Python rerun passed as above.
Ruff is not clean: existing Depends-default B008 plus scoped import/test-style
findings are recorded rather than hidden by a suppression.

Independent review found two Important edge cases (rejected intent trapping the
view; mixed-case hostname failing binding). Each received a failing regression,
minimal fix and passing focused tests (12 backend / 8 UI). Definitively rejected
intent clearing requires a rejected POST plus a subsequent authenticated lookup
with no job; a transient failure/lookup miss alone never enables dismissal.
Two process tests initially failed only in the full suite because parent cached
hash settings differed from spawned-child environment; passing the effective
synthetic test pepper fixed the harness without altering production hashing.

## Release and remaining gates

Agent/installer inputs and archive are unchanged. Existing immutable release:
`nimbusops-agent-1.0.0rc2-dualmode1-ubuntu24.04-amd64.tar.gz`, SHA-256
`8f0a715761aff04920201409c95d648450329d68acb1e41a616c5e131637d7d9`.
Rebuilding unchanged agent bytes would not attest to new control-plane code;
the local source commit identifies this sprint instead.

Still required: authorized disposable Ubuntu target and isolated Linux HTTPS
control-plane/worker, verified SSH trust and install/reset authority; verified
restricted Katrina online-backup copy rehearsal; real SSH/systemd/interruption/
identity-preservation gates. Eight dependency-package advisory dispositions and
existing static-check limitations remain open as documented in the baseline.
