# Katrina dual-mode Add Server — upgrade readiness

## Verdict: NO-GO for live upgrade (local acceptance snapshot)

Current reliability follow-up: `DUAL_MODE_RELIABILITY_ACCEPTANCE.md` supersedes
baseline A/B/C status after local regression verification. Live/real-VM gates
remain NO-GO; historical acceptance below is scoped to its frozen revision.

Local acceptance resumed without infrastructure on 2026-11-20. See
`DUAL_MODE_PARTIAL_ACCEPTANCE.md` for current results and commit resolution,
`DUAL_MODE_REVIEW_FINDINGS.md` for three unresolved Important blockers, and
`DUAL_MODE_DEPENDENCY_ASSESSMENT.md` for all eight advisory dispositions.
Historical implementation evidence below is retained, not final sign-off.

No deployment is authorized. No live Katrina, existing Azure VM or DavidLab
production changes were performed during implementation. No push or merge.

Candidate worktree: `dual-mode-onboarding`, baseline `8203d46`, local committed
snapshot. UTC serialization fix carried forward from `c0255d4`, independently
regression-tested. Do not deploy a moving/uncommitted tree: review and freeze a
candidate revision and artifact hashes first. The local snapshot is frozen but
not approved: recovery and ownership findings remain unresolved.

## Implementation and evidence

- Manual Bootstrap remains the existing wizard, token API, pinned release and
  enrollment/identity protocol, selected explicitly from Add Server.
- Automatic Setup lists server-authorized SSH targets only; target configuration
  is not accepted from browser input. Fixed read-only preflight reports identity,
  OS and proposed changes, then requires explicit approval.
- Existing provisioning tables store plans, single-use confirmation, exclusive
  ownership and audit events. No schema additions are currently required.
- Separate worker commits admission before dispatch. Restart/disconnect never
  causes blind redispatch. Uncertain outcomes retain ownership for reconciliation.
- Success requires the job's consumed bootstrap token, host heartbeat and an
  actual fresh telemetry row. No Docker permissions are granted.
- Latest Python full suite: **479 passed, 1 skipped**, three
  dependency deprecation warnings (68.56s). Targeted retry/disconnect suite:
  **7 passed**.
- Frontend baseline: **146 passed**; initial automatic/manual targeted tests:
  **7 passed**; latest full frontend suite **147 passed**, TypeScript/Vite build
  passed. Latest rerun including confirmation-flow test: **148 passed** in 25
  files (8.16s).
- `npm ci --ignore-scripts` reported **8 dependency vulnerabilities** (5 moderate,
  1 high, 2 critical). No forced dependency upgrade attempted; investigate reachability
  and remediation before release.

## Outstanding acceptance gates

1. Fresh-context review and any important fixes.
2. Expand authenticated API, concurrency, preflight/confirmation UI and retry tests.
3. End-to-end manual installation on a disposable clean Ubuntu 24.04 amd64 VM.
4. End-to-end automatic installation on a separately authorized disposable clean
   Ubuntu 24.04 amd64 VM, using isolated API/database/worker and HTTPS artifacts.
5. Real host-key mismatch, authorization rejection, interrupted install, worker
   restart, duplicate submission and safe retry acceptance.
6. Verify installer adapter against the exact pinned archive on Ubuntu. Unit
   transport tests do not prove sudo/systemd/package-manager behavior.
7. Static analysis/security validation and final full suites/build.

Static validation update: new files were Black-formatted. Scoped strict mypy
with `--follow-imports=silent` passes for the four new production modules;
whole-import strict checking still reports existing-module annotation errors.
Ruff still reports FastAPI dependency-default style findings; not a clean lint
gate. `git diff --check` passed (line-ending warnings only).

## Independent review and fix pass

Review verdict was NO-GO with five important findings. Fixes implemented:
- Conditional ownership release matches job, generation and HELD disposition.
- Worker token creation and job linkage commit together; ordinary token conflict
  becomes a pre-dispatch failure rather than terminating the worker.
- A process-shared nonblocking kernel lock serializes dispatch/reconciliation for
  this single-host SQLite worker. Distributed/network-filesystem workers are not
  supported. Crash releases the lock; admitted jobs are still never redispatched.
- Automatic installer adapter places the short-lived bootstrap file in
  `/dev/shm` with restricted ownership and cleanup; persistent agent identity
  remains unchanged. tmpfs/swap policy still requires operator verification.
- Browser sessionStorage stores only the nonsecret job UUID for reload/method
  recovery; the API reauthenticates job reads. No tokens/keys/passwords persisted.

Final regression evidence after fix pass/formatting: **484 Python tests passed,
1 skipped**, three dependency warnings (76.16s); **148 frontend tests passed**
(25 files, 9.49s); TypeScript/Vite build passed; Black check passed (five files).
Race tests are not yet a full multi-process stress test.

No disposable VM endpoint or scoped SSH credential reference has been supplied.
Existing Azure VMs are explicitly excluded and are not substitutes for these gates.

## Operator configuration (future isolated test/deployment only)

`NIMBUSOPS_SSH_TARGETS_FILE` points to a root/operator-controlled JSON file outside
the repository and web root; absent configuration disables automatic target listing.
Each target includes literal IP, port, SSH username, expected hostname,
`/etc/machine-id`, absolute private-key reference and dedicated known-hosts file.
Verify host key and machine binding out of band. Use short-lived/scoped SSH keys;
restrict files and the provisioning process account. Never store key/password
contents in database, browser, source control or logs. SSH uses strict known-host
verification, no password/keyboard-interactive auth, no agent forwarding or ambient
user configuration. Passwordless sudo authority must be explicitly reviewed;
an unrestricted root installation channel is not a least-privilege deployment.

Worker invocation from the candidate root:
`python -m backend.app.provisioning.worker`, with the **isolated** database and
`NIMBUSOPS_PROVISIONING_ORIGIN` configured. Never inherit live environment settings
for a test. No worker was started against Katrina.

## Proposed in-place upgrade procedure — NOT executed

Requires separate deployment approval after all acceptance gates pass.
Use `docs/BACKUP_RESTORE.md` as the repository backup/restore reference; this
package adds scratch-specific preservation and post-backup enrollment cautions.

### 1. Freeze and preflight
- Record candidate commit and frontend/backend/archive SHA-256 digests.
- Confirm scratch root `/home/david/nimbusops-demo-8203d46`, API `127.0.0.1:18180`,
  Caddy `127.0.0.1:18181` and existing public URL. Preserve Caddy/tunnel unchanged.
- Record existing host IDs, credential versions, enrollment/revocation flags,
  heartbeat/telemetry freshness and row counts **without reading secret values**.
- Back up existing code/artifacts and restricted configuration privately.

### 2. SQLite online backup and migration rehearsal
- Use SQLite online backup API into a new restrictive backup directory, not a
  plain file copy of an active WAL database. Keep database/pepper configuration
  together in restricted custody; never print or commit secrets.
- Run `PRAGMA integrity_check` and `PRAGMA foreign_key_check` on the backup.
- Restore a backup copy into an isolated rehearsal directory; run candidate
  migrations twice and compare schemas, markers and preserved host/credential
  fields. Expect no destructive changes or additional migration for this feature.
- Verify the old backend can still read the rehearsed database; otherwise stop.

### 3. Approved promotion
- Stop only the approved scratch backend during a bounded maintenance window.
  Do not restart production, Caddy or tunnel. Stage candidate frontend/backend
  with known rollback artifacts; preserve scratch.env and database.
- Keep SSH automatic setup disabled until target policy and worker privilege
  review pass; start only the explicitly approved separate scratch worker.
- No reenrollment, credential rotation, SQLite reset or target VM change is part
  of upgrading the control plane.

### 4. Health and preservation gates
- Local/public health 200, database OK; ADMIN and VIEWER session behavior intact.
- Same-origin `/api/v1` and `/releases` unchanged; manual command hash unchanged.
- Both existing Azure host IDs and credential versions match pre-upgrade values.
- Observe at least three fresh heartbeat/telemetry cycles per existing host;
  no revoked flags, duplicate host identities or Docker permission changes.
- Smoke-test method selection/preflight using only an approved disposable target;
  no installation on existing agents. Confirm sanitized job audit visibility.

### 5. Rollback
- Stop the new scratch worker first to prevent new dispatch; do not redispatch
  admitted operations. Preserve job state, token metadata and target evidence.
- Restore old backend/frontend artifacts and exact configuration without changing
  URL/tunnel. Because changes are additive/no new schema, prefer code rollback
  with the current DB to avoid losing telemetry/enrollment history.
- Restore DB backup only with separate explicit data-loss approval and after
  reconciling all post-backup admissions/enrollments. Never blindly restore an
  old DB that would orphan credentials issued after the backup.
- Re-run health, identity and three-cycle freshness gates. Rollback of control
  plane code does not uninstall a remotely installed agent; reconcile separately.

## Authorization boundary

This package is preparation, not permission. Final GO requires real VM acceptance,
resolved review findings and separate user approval of the exact deployment plan.
