# Dual-mode partial acceptance — 2026-11-20

## Decision: NO-GO

**Katrina deployment: NO-GO. Real-VM acceptance sign-off: NO-GO.**
Local candidate preparation is complete enough to inspect/reproduce and run
isolated characterization tests, but **not ready for a clean real-VM acceptance
sign-off** until the Important findings are resolved. No live access, production
mutation, SSH credential assumption, push, merge, deployment or restart occurred.

## Immutable candidate identity

- Reviewed implementation/source snapshot: `b812976b14d74e8eff264a852b783d3bd2b9e0f3`.
- Final candidate: the local commit containing this report and release pins.
  Resolve with `git log -1 --format=%H -- docs/DUAL_MODE_PARTIAL_ACCEPTANCE.md`.
  The final response records the literal SHA after commit; a report cannot embed
  the hash of its own containing commit without a circular dependency.
- Release: `nimbusops-agent-1.0.0rc2-dualmode1-ubuntu24.04-amd64.tar.gz`.
- SHA-256: `8f0a715761aff04920201409c95d648450329d68acb1e41a616c5e131637d7d9`.
- Provenance: `deploy/releases/dualmode1-provenance.json`.
- Two deterministic builds are byte-identical. All 19 archive members are regular
  files, with safe relative paths, zero uid/gid/mtime. Exact installer/agent source
  bytes and nine wheel hashes match. Agent inputs are unchanged from demo1, so
  unchanged digest is expected despite the new release identifier. No Ubuntu
  package installation is implied. Previous immutable release is retained.

## Local verification evidence

Pre-freeze full suite: **484 Python passed, 1 skipped, 3 dependency warnings**;
**148 frontend passed in 25 files**; TypeScript/Vite production build passed.
Added acceptance-only tests (no product changes): **3 passed**, including:

- Four independent spawned processes racing on one SQLite job admit it exactly
  once; remaining three return no job. This is a bounded CAS test, not stress.
- Separate-process worker-lock exclusion and reacquisition after release.
  Exercised Windows locking only; Linux flock/crash behavior remains unverified.
- Synthetic database online backup, candidate migration twice, stable schema,
  integrity `ok`, no FK violations, byte-for-byte host/credential/telemetry
  preservation; credential version 7 and Docker-disabled flag retained.

Combined new acceptance and existing migration suite: **7 passed**. This is
synthetic evidence only, not a rehearsal against Katrina data or proof that the
old deployed backend reads the actual migrated snapshot.

Scoped static checks: strict mypy with silent imports passes four new modules;
Black check passes six scoped files. Ruff **fails** on nine B008 findings in
FastAPI `Depends` defaults; matching existing framework style is not a clean lint
gate. Whole-project strict mypy is not claimed clean. `git diff --check` passes.

The post-commit full-suite/build run is recorded in the final session response
against the literal final SHA; do not reinterpret pre-freeze counts as that run.

## Audit and ownership

Complete tracked and relevant untracked candidate files reviewed, including an
independent fresh-context reviewer. No unrelated functional work found beyond
the intended UTC serialization carry-forward. Incidental BOM/mojibake corrected.
Existing `ruff-results.json` remains untracked, untouched and excluded from commits.

Gitleaks redacted directory scan of candidate files found no secrets (limited
to current candidate contents, not all repository history). Candidate ACLs are
owned by current Windows user with user/SYSTEM/Administrators grants, no broad
writable ACEs. Git file modes are regular 100644. Server-side key/policy custody,
sudo privileges and Linux filesystem ownership have **not** been validated.

## Review blockers (not waived)

See `DUAL_MODE_REVIEW_FINDINGS.md`:

1. Confirmation committed but response lost cannot recover its job reference.
2. Automatic ownership is not host-bound, bypassing the existing manual-token
   ownership exclusion for automatically enrolled hosts.
3. Persisted terminal job has no supported “add another”/dismiss path.

Minor deferred: malformed operator policy shape can escape sanitized 503 errors.
These are recorded, not fixed during this acceptance-only pass. A local snapshot
commit does not represent approval of the implementation or a clean review.

## Security advisories

Eight affected packages: **5 moderate, 1 high, 2 critical**. Full disposition is in
`DUAL_MODE_DEPENDENCY_ASSESSMENT.md`. Six packages are dev/build/test-only, including
both critical aggregates (Vitest/tinypool); never expose their servers and run
trusted tests only. Production-only audit retains two moderate React Router
packages sharing the same underlying advisories. SSR hydration is not configured;
no externally supplied redirect sink was identified, but backslash handling is
not formally proven safe. No advisories are declared fixed or unconditionally
accepted. Coordinated major dependency upgrades need separate compatibility work;
no `npm audit fix --force` or lockfile change was performed.

## Remaining infrastructure requirements

Only infrastructure-dependent tasks are BLOCKED:

- Explicit disposable Ubuntu 24.04 amd64 authorization (not existing Azure VMs),
  literal IP/port/user, secure server-side scoped key reference, expected hostname
  and machine ID, independently verified fingerprint/known_hosts binding.
- Install/sudo/systemd, interruption/reboot and snapshot/reimage authority; clean
  reset between Manual and Automatic methods, or two clean authorized targets.
- Isolated Linux API/database/worker location, reachable HTTPS `/api/v1` and
  `/releases/` origin, Ubuntu repository access; no live environment inheritance.
- Verified restricted Katrina SQLite online-backup snapshot/path/hash/capture
  time, supplied through an approved process. Rehearse on a second copy only.

Not established: real host-key mismatch/rejection, sudo/systemd installation,
fresh real-agent token consumption/heartbeat/telemetry, duplicate/interruption/
retry/recovery, tmpfs/swap policy, target identity preservation and Docker exclusion
on Ubuntu, Linux multi-process behavior, actual Katrina-copy migration/backward
readability. Separate approval is still mandatory before deployment or push.
