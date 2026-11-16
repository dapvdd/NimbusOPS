# NimbusOps v1.2 Sprint 5 — full provisioning design

**Status: DESIGN FOR APPROVAL — NOT AUTHORIZATION TO IMPLEMENT OR DEPLOY.**

Date: 2026-11-17. Baseline: `f3a8809c74a227dd41a801da071e9617105f8814`.
Branch: `sprint/zero-touch-provisioning`. Isolated worktree: `sprint5-full-design`.
Normative terms MUST/MUST NOT define acceptance requirements; recommendations below are designer calls, not operator-approved deployment configuration.

## 0. Approval, scope and evidence

The operator approved the immutable baseline, isolated branch/worktree, database-backed separate worker, SQLite WAL on supported local storage, and agent installation/lifecycle on existing explicitly authorized Azure VMs. VM creation/deletion, networking changes, live deployment and application implementation are excluded. Existing auth, host IDs, telemetry and Docker contracts must be preserved. Recovery needs independent management authority.

This document completes the selected architecture, contracts and dependency-level TDD work packages. Its approval and a subsequent implementation plan/approval are still required before code. No dependency installation or application tests are needed to write this document; historical baseline results are evidence only, not new verification.

### Evidence inspected

| Evidence | Finding / design consequence |
|---|---|
| Baseline `backend/app/models/__init__.py:22-58,131-207` | Stable hosts, credential version/grace, Docker operations and bootstrap tokens exist; provisioning is a separate domain. |
| Baseline `backend/app/core/db.py:24-49` | SQLAlchemy, WAL, FK enforcement and 5s busy timeout already exist; use existing migration mechanism, not a new ORM. |
| Baseline `backend/app/services/hosts.py:79-170,188-257` | Enrollment helper commits internally; auth returns only Host; telemetry also updates last_seen. New atomic protocol must not call committing helper inside a larger transaction. last_seen is insufficient verification. |
| Baseline `backend/app/api/agents.py:53-68,108-154` | Preserve legacy enrollment/heartbeat/telemetry; add opt-in managed protocol without breaking old agents. |
| Candidate `699883e` | Source material for effective lifecycle, mode and intent guards only. Port individually with tests; not a baseline or cherry-pick decision. |
| Candidate `49029a9`, `agent/nimbusops_agent/main.py`, re-enroll/apply helpers | Reject restoration of old identity after committed enrollment and helper-only heartbeat success. File replacement does not reload an already constructed Sender. |
| Prior audit `SPRINT5-AUDIT-AND-PROPOSAL.md` in approved temp artifacts | Source-backed OS/provider/UI gaps and immutable baseline results: backend 187, integration 8, agent 104 passed/1 skipped, frontend 70, build passed. Existing dependencies reused; not real startup/Azure acceptance. |

Active UX work was not imported. Its observed tip advanced to `d770386` during continuation; no reset/rebase/stash changes are part of this work.

### Approaches and selection

1. **Selected by operator:** DB-backed orchestration and separate worker. Fits existing SQLAlchemy/SQLite; requires explicit dispatch uncertainty and remote ownership protocol.
2. External workflow engine: additional service and deployment burden; does not solve target credentials or uncertain external effects. Deferred until measured scale requires it.
3. Existing Docker command queue: cannot bootstrap missing/revoked agents and is not a management trust root. Remains independent.

### Outcome and anti-goals

An ADMIN chooses an already manageable target, reviews exact privileged changes, authorizes a job, and sees durable progress ending in a correctly mapped host with a real authenticated persistent-runtime heartbeat and fresh telemetry. A provider command exit code or old ONLINE badge is never success. No arbitrary command execution API, automatic privilege grant, network scan, silent Docker enablement, synthetic telemetry or automatic identity merge.

## 1. Components and trust boundaries

| Component | Owns | Cannot do |
|---|---|---|
| Dashboard | Provider selection, safe validation/review, submission, timeline/history/recovery | Hold cloud, bootstrap or agent secrets; decide authorization or success |
| API / provisioning service | Operator auth/CSRF, target scope, canonical review, idempotency, transactional state/events, evidence ingest | Execute remote installation in request/background web tasks |
| Separate worker | Lease claims, policy/deadlines, reconciliation, typed provider calls, evidence evaluation | Bypass target ownership, approval expiry or revocation |
| Provider adapter | Authorized discovery/preflight, fixed install/lifecycle dispatch, lookup/cancel, sanitized receipts | Accept user command/script text; return raw sensitive output |
| Target manager/installer | Privileged fixed action, OS lock/journal, pinned releases, credential handoff, service control | Create VMs; restore invalid credentials; claim control-plane success |
| Persistent agent | Existing monitoring, current identity, opt-in job proof, graceful stop | Use revoked credentials to request recovery |
| SQLite | Jobs, intents, ownership, identity generations, events, receipt ordering | Stop a command already running remotely |

Flow: operator session → scoped discovery → non-mutating validation → immutable review → approved job + target ownership → worker intent → independent management channel → target journal/installer → managed enrollment → persistent service → authenticated heartbeat/telemetry receipts → verifier → SUCCEEDED.

API and worker run on one control-plane machine with the same supported local DB file. Start with one worker process, maximum 2 concurrent jobs globally, 1 per target, 1 Azure dispatch per connection; all are configurable downward. Recovery correctness must still hold with two competing worker processes during restart. No multi-node/shared-NFS/SMB database support. Worker readiness requires correct schema, key configuration, local storage declaration, WAL/FK/required indexes and clock health. Unsupported/unknown storage is setup-required, not an inferred safe filesystem.

Provider connection configuration is a protected server-side versioned file/secret-store reference, not browser CRUD in Sprint 5. No cloud client secrets in DB. Operator enrollment authority, provider authority and agent authority are separate. Compromise of a privileged target manager is within the trusted-host boundary; this is management-channel identity assurance, not hardware attestation.

## 2. Canonical identity, validation and approval

- `target_id` is an opaque UUID. `canonical_key` is stable and unique: Azure normalized full ARM VM ID plus observed `vmId`; SSH connection plus pinned machine identity; local manager installation UUID plus Windows machine identity. Display name/IP/hostname never grants authority.
- Azure VM recreation under the same ARM ID changes `vmId` and invalidates validation/mapping. SSH host-key change or machine identity change also invalidates approval.
- Map one target to at most one host and one host to at most one target. New cross-provider aliases require explicit ADMIN-assisted mapping and independent-channel identity check before mutation. Discovery of an existing NimbusOps state on an unmapped target blocks INSTALL; never overwrite it by matching hostname.
- Normalize new hostname inputs once (trim, lowercase ASCII DNS label/FQDN, reject trailing dot, whitespace/control/non-ASCII and `sim-` namespace, max 253). Use identical normalized value in review, capability and enrollment. Do not rewrite legacy hostnames; case/alias collision yields IDENTITY_MAPPING_REQUIRED. Existing mapped host recovery uses host ID, not lookup by hostname.
- Validation is read-only: authorized connectivity, pinned target identity, exact supported OS/arch, guest agent/manager readiness, disk space, pinned artifact availability, HTTPS egress and no conflicting managed operation. It may run a fixed read-only remote probe **only if the connection policy explicitly permits that privileged probe**; otherwise report setup-required. GET discovery does not run scripts.
- Validation result expires in 10 minutes. Store immutable reviewed plan JSON and SHA-256 fingerprint of canonical JSON including target identity, connection config revision, operation, expected host/credential generation, artifact digest, config version/hash, privileged actions and support policy revision. Mutable free-text labels are not part of authorization.
- Job submission includes validation ID, fingerprint and explicit confirmation. Server verifies exact match, active ADMIN session and connection policy; atomically consumes validation for one job. Idempotent replay returns the same job. Approval lasts 15 minutes for a **new external dispatch**, not for reconciliation of already-dispatched effects. Changed plan, expired approval or retry needs a fresh validation/confirmation. No automated approval refresh.

## 3. Durable state machine

Seven states only: PENDING, VALIDATING, RUNNING, VERIFYING, SUCCEEDED, FAILED, CANCELLED. Job state is not host connectivity state.

| From → to | Guard and transactional effects |
|---|---|
| create → PENDING | Scope/auth/review valid; idempotency reservation, target ownership, snapshot and CREATED event in one commit |
| PENDING → VALIDATING | Worker lease CAS succeeds; revalidate policy, mapping and credentials without changing target |
| VALIDATING → RUNNING | Prerequisites still valid, exact approval current; fixed action ready; persist dispatch intent before external call |
| RUNNING → VERIFYING | All mutating remote steps known terminal and installation/service journal confirms expected activation; preserve ownership |
| VERIFYING → SUCCEEDED | Operation-specific evidence predicate in §7 holds; atomic state/event/evidence pointers and release ownership |
| PENDING/VALIDATING → FAILED | Definitive validation/policy failure; no unresolved external effect; release ownership |
| RUNNING/VERIFYING → FAILED | Definitive failure, prior effects reconciled and no active remote mutation; report partial effects and retain valid identity |
| Any nonterminal → CANCELLED | Cancel requested and no submission possible, or remote stopped/finished with safe known disposition; release ownership only after reconciliation |

Terminal states are immutable; retry creates a linked child job. No RUNNING → PENDING reset. `reconciliation_required`, `reason`, `next_check_at`, `dispatch_blocked` and `cancel_requested_at` are orthogonal durable fields. Unknown effect stays RUNNING/VERIFYING even after deadline, with prominently visible “needs reconciliation”; it does not become FAILED merely to clear a queue.

Transition and event commit together under job revision/lease generation and ownership generation predicates. A late stale worker cannot commit a transition, release ownership or write credentials. Success versus cancel uses CAS: if cancellation intent commits before success, reconcile and end CANCELLED with effects disclosed; if success wins first, cancellation returns 409 JOB_TERMINAL. Cancellation never means uninstall, credential rollback, VM deletion or guaranteed interruption.

Step order: REVALIDATE → PREPARE_ARTIFACT → DISPATCH_INSTALL_OR_ACTION → RECONCILE_REMOTE → CONFIRM_ACTIVATION → VERIFY_RUNTIME. Re-enroll/rotate include PREPARE_IDENTITY and COMMIT_IDENTITY inside the target journal. DIAGNOSE has read-only remote execution and requires a fresh job-bound persistent-runtime receipt to succeed; offline collection can return useful partial diagnostics but does not falsely satisfy provisioning success.

## 4. SQLite schema and migration contract

Schema notation: UUID text PKs, integer millisecond UTC timestamps, bounded text enums with CHECK, booleans 0/1, hashes fixed 64 hex, JSON serialized canonical text with size/schema validation. All provisioning FKs use RESTRICT; records are not cascade-deleted with hosts. Existing tables remain intact.

| New table | Columns / integrity constraints |
|---|---|
| `provisioning_connections` | id PK, provider enum, display_name, config_revision, policy_hash, enabled; only nonsecret metadata mirrors server config |
| `provisioning_targets` | id PK, connection_id FK, canonical_key UNIQUE, observed_identity_hash, host_id nullable UNIQUE FK hosts, mapping_revision, mapping_status, discovered_at; UNIQUE(connection_id, canonical_key) |
| `provisioning_validations` | id PK, target_id FK, actor_id FK operators, plan_json<=32KiB, plan_hash, config_revision, mapping_revision, observed_identity_hash, created_at, expires_at, consumed_by_job_id nullable UNIQUE; only passed validations consumable |
| `provisioning_jobs` | id PK, target_id FK, operation enum INSTALL/REENROLL/ROTATE/RESTART/DIAGNOSE/UPGRADE, expected_host_id nullable FK, validation_id UNIQUE FK, requester_id FK, approval_hash, approved_at, approval_expires_at, plan_json<=32KiB, state CHECK, revision>=0, step, deadline_at, cancel_requested_at, reconciliation_required, dispatch_blocked, reason_code, next_check_at, lease_owner nullable, lease_until nullable, lease_generation>=0, retry_of_job_id nullable FK, created_at, updated_at, completed_at; terminal iff completed_at not null |
| `provisioning_requests` | actor_id, route_scope, idempotency_key<=128, request_hash, job_id FK; composite PK(actor_id,route_scope,idempotency_key). Retain as long as job; never recycle a key to another job |
| `provisioning_ownership` | target_id PK/FK, host_id nullable UNIQUE FK, owner_job_id UNIQUE FK, generation>=1, disposition HELD/RECONCILING/RELEASED, acquired_at, released_at; row/generation survives release |
| `provisioning_attempts` | id PK, job_id FK, step_key, ordinal 1..3, dispatch_id UNIQUE, ownership_generation, intent_hash, status INTENT/ACCEPTED/COMPLETED/NOT_SUBMITTED/UNKNOWN, provider_handle nullable, provider_receipt_json<=8KiB, started_at, deadline_at, next_attempt_at, finished_at, error_code; UNIQUE(job_id,step_key,ordinal) |
| `provisioning_events` | job_id FK, sequence>=1, at, actor_kind/id, code, state, step, safe_detail_json<=4KiB; PK(job_id,sequence); append-only; allocate sequence by job revision transaction, not unlocked MAX+1 |
| `provisioning_grants` | id PK, job_id FK, dispatch_id FK attempts, target_id FK, expected_host_id nullable, intent, token_hash UNIQUE, expires_at, consumed_at nullable, candidate_hash nullable, result_host_id nullable FK, result_credential_version nullable, revoked_at; no plaintext token |
| `provisioning_credential_commits` | id PK, job_id FK, grant_id UNIQUE FK, host_id FK, previous_version, committed_version, candidate_hash, committed_at; UNIQUE(host_id,committed_version); audit, not secret escrow |
| `provisioning_challenges` | id PK, job_id FK, host_id FK, credential_version, runtime_instance_id, nonce_hash UNIQUE, activation_sequence, expires_at, consumed_at nullable |
| `provisioning_receipts` | id INTEGER PK AUTOINCREMENT (global server order), job_id FK, host_id FK, kind HEARTBEAT/TELEMETRY, credential_version, matched_slot CURRENT/GRACE, runtime_instance_id, challenge_id nullable FK, sample_sequence, received_at, payload_hash, safe_metadata_json<=4KiB; UNIQUE(job_id,kind,runtime_instance_id,sample_sequence) |

`provisioning_validations.consumed_by_job_id` is a logical reference verified transactionally to avoid a circular insertion dependency; all other listed FKs are database-enforced. Add indexes jobs(state,next_check_at,lease_until), jobs(target_id,created_at,id), events(job_id,sequence), attempts(job_id,status), receipts(job_id,id), grants(job_id,expires_at). New auth evidence references the existing Host credential_version; no blanket backfill or token replacement.

Migration procedure: quiesce writes for a bounded maintenance window; online SQLite backup API (includes WAL), integrity_check and FK check, inventory schema/indexes and duplicate legacy hostname/token anomalies; apply new tables/indexes/checks through `backend/app/core/migrations.py` conventions, record schema revision, verify required guards, restart with provisioning dispatch disabled. Repeat migration must be a no-op. Constraint failure fails readiness with remediation; never delete collisions or silently skip a unique index. No application startup DDL race across worker/API. Enable provisioning only after schema readiness. Test upgrade from actual f3a8809 fixtures and existing populated DB copies with disposable data; no production copy/secrets in tests.

Use short `BEGIN IMMEDIATE` transactions for claims/ownership/identity commits; never hold a transaction across network I/O. Busy timeout 5s, at most 3 jittered transaction retries within request deadline, then 503 DB_BUSY/Retry-After; idempotency still protects replay. Read the DB clock for lease comparisons. Wall-clock jumps conservatively stop new dispatch and reconcile; they cannot authorize a second attempt. Require `synchronous=FULL` for new durability guarantees and verify its setting. DB backup/restore and physical disk durability remain operational prerequisites.

## 5. Leases, fencing, dispatch and reconciliation

### Claim and ownership

Default worker lease 30s, renewal every 10s. Claim atomically increments lease_generation for due nonterminal jobs whose lease expired. All writes predicate on job ID, owner, generation, unexpired lease and job revision. Target ownership is a separate monotonic generation, acquired at submission; it NEVER expires with a worker lease or job deadline. Worker loss gives a successor reconciliation rights, not redispatch permission.

Host lifecycle mutators (manual rotate/re-enroll/revoke/environment or executor-mode change that affects approved config) must consult this ownership guard in the same transaction. Revoke is a security exception: it is always permitted to ADMIN, atomically revokes grants/challenges, blocks dispatch and marks active job reconciliation-required; it never waits for provisioning. Verifier predicates include current host revocation/version and cannot succeed after concurrent revocation. Docker enable/dispatch must not cross an identity-changing job: reject new Docker mutations with 409, quarantine pending operations, drain/reconcile running Docker operations before identity mutation. Monitoring reads and normal telemetry continue. No changes to Docker authorization semantics or automatic reauthorization of queued operations.

### External effect protocol

1. Under valid lease/approval/policy/ownership, commit INTENT with immutable dispatch_id, fixed plan hash, target generation, deadline and correlation handle chosen **before** sending. Mint a just-in-time grant only when channel delivery is ready.
2. After commit, recheck dispatch permission immediately before call. Target manager also verifies job/dispatch/generation and cancellation/revocation with backend immediately before any new privileged step; if unreachable it does not begin a new step. This narrows but cannot eliminate a race with an already-running OS action.
3. Adapter returns NOT_SUBMITTED (definitive no external acceptance), ACCEPTED(handle), COMPLETED(receipt), or UNKNOWN. Network timeout, 5xx after send, lost response, worker death or missing operation immediately after send is UNKNOWN.
4. Persist result under fences. Lease loss discards write authority, not the remote receipt: successor looks it up using persisted correlation and target journal.
5. Successor reconciles provider resource and protected target journal; never blindly repeats PUT/SSH/process launch. A remote manager journals dispatch_id/plan hash and holds an exclusive OS lock for the full effect; duplicates return status, conflicting plans/generations are rejected. Persist terminal result with fsync/atomic replacement before releasing lock. Journal retention at least job retention (default 90 days), and unresolved entries never pruned.
6. An INTENT with no acknowledged submission is still uncertain. “Not found” after timeout is not proof of nonexecution. Only a provider's validated definitive rejection, or target journal/status with proven no live process and no pending request, permits NOT_SUBMITTED. Otherwise block for independent managed reconciliation. No admin “force retry anyway” action.

No exactly-once claim is made for transport. Safety guarantee is **no automatic duplicate external execution after uncertainty**; availability may stop indefinitely. Remote fencing/locking is additional defense, not a claim that a DB lease can kill an old process. A fresh target operation generation cannot be issued until previous effects are known terminal.

### Time and retry policy

Defaults: discovery/HTTP connect 10s; validation 60s; grant TTL 5min; remote action 10min; activation 2min; runtime verification 3min; overall job 20min. Provider request timeout is not remote action timeout. Three safe automatic attempts per step, full jitter base 5s/cap 60s; no retry beyond approval/deadline. NOT_SUBMITTED transient failures and safe read/status polls can retry. Permission/scope/identity mismatch, consumed/expired grant and malformed config require correction; no automatic credential remint for an uncertain dispatch. Expired approval before any dispatch is FAILED APPROVAL_EXPIRED; after dispatch reconciliation continues, but any further mutating step requiring new approval blocks visibly. Retry API creates a child job only from FAILED/CANCELLED with resolved ownership and fresh validation. SUCCEEDED jobs may receive a separate explicit operation, not retry.

## 6. Provider adapter contracts and support matrix

Typed protocol (design, not implementation):

| Method | Input → output / guarantees |
|---|---|
| `capabilities(connection)` | configured policy → setup state, support matrix, allowed operations, secure_delivery and reconciliation capability flags |
| `discover(connection,cursor,limit)` | server allowlisted scope → opaque target descriptors; never arbitrary addresses |
| `validate(target,plan)` | fixed read-only checks → identity evidence, prerequisites, privilege list; no installation |
| `dispatch(intent,secret_channel)` | immutable intent → four-valued outcome; MUST NOT automatically retry an uncertain mutating SDK call |
| `reconcile(intent)` | persisted correlation → ACCEPTED/RUNNING/COMPLETED/DEFINITIVELY_NOT_SUBMITTED/UNKNOWN plus safe evidence |
| `request_cancel(intent)` | cancellation intent → UNSUPPORTED/REQUESTED/CONFIRMED; never equate request with completion |
| `diagnostics(intent)` | fixed allowlist → bounded sanitized structured data |

All adapters reject scripts, shell fragments, user URLs, arbitrary artifact sources, provider handles outside configured scope and unsupported OS. Error taxonomy: SETUP_REQUIRED, AUTHORITY_UNAVAILABLE, PERMISSION_DENIED, TARGET_OUT_OF_SCOPE, IDENTITY_MAPPING_REQUIRED, TARGET_UNREACHABLE, UNSUPPORTED_OS, ARTIFACT_UNAVAILABLE, SERVICE_START_FAILED, PROVIDER_OPERATION_UNKNOWN, CREDENTIAL_COMMIT_UNKNOWN, HEARTBEAT_TIMEOUT, TELEMETRY_TIMEOUT, APPROVAL_EXPIRED, CANCEL_NOT_CONFIRMED. Sanitized codes/remediation only; no raw stderr exception objects.

### LOCAL_WINDOWS — recommended call

Means the explicitly configured Windows **control-plane/worker machine**, not the browser's PC. Initial adapter enabled only when worker runs on that target and a pre-established privileged local manager is installed/authorized by an operator. Communicate through an ACL-restricted named pipe with peer identity checks, fixed request schema and pinned manager installation ID. API runs unprivileged; manager only accepts approved fixed operations and server-validated intents. Missing manager or backend on Linux → setup-required; never elevate silently, remotely install the manager, or use UAC from the dashboard. A remote Windows fleet manager is out of scope unless separately designed/approved.

### GENERIC_LINUX — recommended call

Use preconfigured SSH key authentication, pinned host key, fixed allowlisted endpoint and restricted management account. Secret key remains in server OS credential store or protected file reference. No browser key/password upload or auto-accept host key. A root-owned fixed manager executable is pre-established with tightly scoped sudo permission; no `sudo sh`, arbitrary shell or general root login grant. SSH subsystem/framed stdin transfers the grant and request without argv/environment/script interpolation. No shell expansion of target labels. Journal/status path survives SSH disconnect; inability to query it yields UNKNOWN, not re-execution. Missing channel/manager is operator-assisted setup.

### AZURE_VM — recommended call

Use **Managed Run Command**, not Action Run Command, as named child operation resource for durable lookup; unique name `nimbusops-<dispatch_uuid>` persisted before creation. Never update/re-PUT an uncertain resource or delete it to make a retry appear safe. Read instanceView execution state separately from ARM provisioning state and check target journal/activation; neither equals success.

Server uses a specifically selected managed/workload identity (no ambient developer credential fallback), tenant/subscription/RG/VM allowlist and expected VM identity. Custom role candidate: `Microsoft.Compute/virtualMachines/read`, `Microsoft.Compute/virtualMachines/instanceView/read`, `Microsoft.Compute/virtualMachines/runCommands/read`, `Microsoft.Compute/virtualMachines/runCommands/write`, and provider LRO read permission if required by the selected API. Exact action spellings/API version must be checked against provider metadata/SDK before enabling, because Learn prose and resource casing differ. No Contributor, VM write/delete, role assignment, networking permissions or automatic guest-agent/VM identity enablement. Resource cleanup/delete is not part of initial adapter; cancellation is cooperative and may remain pending until known terminal.

Run Command carries only fixed nonsecret script and job/dispatch IDs, pinned artifact public/allowlisted HTTPS location and digest. No SAS URLs, tokens or passwords in scripts, parameters, protectedParameters, environment, outputBlobUri or argv. SDK/HTTP request-body logging is disabled. Linux protected parameters become environment values and Windows protected parameters become process arguments according to Microsoft documentation; they are not the chosen secret transport.

**Recommended secure bootstrap:** existing VM has an operator-established, explicitly bound managed identity. Fixed guest manager obtains a token from IMDS for a dedicated NimbusOps bootstrap audience, keeps it in memory and calls the backend exchange endpoint over TLS. Backend validates signature using trusted tenant metadata/JWKS, issuer, audience, exp/nbf, tenant and allowlisted principal object ID; server ARM identity principal binding and vmId must match the exact target. Require system-assigned identity for initial slice, and reject shared user-assigned identities or unvalidated resource claims. Do not trust a client-provided ARM ID. Exchange returns the one-dispatch capability in response body only. Token validation/tenant app configuration and existing VM identity are enablement gates, not deployment actions in this task. Missing identity/audience/egress → setup-required. No fallback token-in-script transport.

Reference consulted 2026-11-17: https://learn.microsoft.com/en-us/azure/virtual-machines/linux/run-command-managed (supported systems, named resource/status lookup, protected parameter behavior). Documentation is not real Azure acceptance. Initial OS allowlist proposed: Ubuntu 24.04 x64 and Windows Server 2022 x64; other distros/architectures, scale sets and sovereign clouds require explicit later certification.

## 7. Credentials, enrollment and causal verification

### Managed enrollment protocol (new opt-in, legacy unchanged)

Avoid a recoverable server-secret vault and lost enrollment response by having the target generate the proposed agent credential **before** enrollment. Use existing secure random token strength and keyed hashing scheme; plaintext exists only in protected target state and TLS request bodies, never persisted server-side.

1. Target manager verifies protected state permissions and acquires OS identity/config lock; stops the existing daemon for identity-changing operations and confirms it exited. Persist journal PREPARED with new random credential, candidate_id, job/dispatch, target binding and expected host/version before sending. fsync file + parent directory (Windows equivalent write-through/replace and verified ACL). No old identity deletion yet.
2. Deliver single-use capability: SSH stdin / local named pipe, or Azure workload-token exchange. Server stores only capability hash, scope, TTL and dispatch. If exchange response is lost, hash-only capability cannot be replayed; **after** channel identity and journal prove enrollment not committed, invalidate prior unconsumed grant and issue a replacement for the same dispatch. If commitment is uncertain, reconcile first.
3. `POST /api/v1/agents/managed-enrollments` sends capability in Authorization, candidate credential in JSON over TLS, job/dispatch/candidate IDs and expected identity. All request/response bodies and auth headers are excluded from logs. Capability cannot authorize generic agent actions or any other job.
4. One DB transaction verifies grant/approval dispatch/target mapping, expected host/version, current revocation intent, operation ownership and candidate hash; consumes grant, creates host or replaces token in **same host ID**, clears all incompatible previous grace, increments version, writes commit record and event. New INSTALL on an already enrolled hostname fails closed. Explicit approved REENROLL can clear revoked status; a later revocation defeats stale grant. ROTATE on revoked host is denied. No helper commits inside this transaction.
5. Response contains host ID, credential_version and commit ID, **not a newly generated secret**. Duplicate same grant + same candidate hash returns the original safe commit metadata, including after grant expiry when already committed; different candidate/dispatch returns 409. Duplicate metadata receipt does not un-revoke a host or authenticate the candidate. A separate current-credential-authenticated status check confirms whether the commit remains current. This removes the “server committed but secret response lost” failure.
6. Manager atomically promotes the protected candidate to active identity after confirmed current commit; records COMMITTED and starts/restarts the daemon. If local promotion fails, keep candidate and reconcile current status using independent management. Never restore precommit credential bytes after commit/uncertainty. Reboot recovery inspects pending journal before starting old runtime. Old backup is forensic/quarantined, not a fallback auth source; remove secret backups after safe completion per retention policy.
7. Persistent daemon loads committed identity/config at process start and constructs a new Sender. v1 uses stop/write/start, not hot reload. Manager confirms service-owned PID/start instance from supervisor and arms a fresh job challenge for that runtime. Helper must not send the qualifying heartbeat. Cross-process lock excludes concurrent manual enrollment/apply. Future reload must reconstruct all senders/workers atomically and is not assumed now.

Independent management grant exchange remains usable for revoked/offline host recovery; revoked agent credential never authorizes exchange. Manual legacy rotation/re-enrollment remains possible only outside held target ownership. Managed jobs use the new safer protocol, not candidate one-shot helper rollback.

### Verification predicate

Auth path yields `AuthContext(host_id, credential_version, matched_slot, is_revoked)` from the actual token comparison, not agent JSON. Preserve public legacy behavior via an internal wrapper if needed; current/grace distinction cannot be inferred from payload.

After supervisor activation confirmation, API stores an activation receipt sequence and issues a random 256-bit challenge (hash only in DB, TTL 3min). Manager securely writes challenge to daemon-only state using the management channel, bound to job/host/current version/runtime_instance_id. Persistent service sends it on the ordinary heartbeat in an optional `provisioning_proof` object; telemetry sends job/runtime/sample identifiers. Normal metadata reporting retains mode/version consistently. New protocol receipts are written in the same transaction as accepted heartbeat/telemetry effects.

SUCCEEDED requires ALL:

1. Exact approved canonical target mapping/observed machine identity and expected host ID; host not revoked and credential version equals committed/intended current version at success CAS.
2. Provider remote action known terminal, manager activation journal matches job/dispatch, supervisor confirms daemon ownership/PID/start identity. A one-shot helper or agent-declared “daemon” boolean is insufficient.
3. Real heartbeat authenticated with CURRENT slot (never GRACE), expected version/runtime instance and unconsumed valid challenge for this job. Server global receipt sequence exceeds activation sequence. Consume challenge atomically with heartbeat receipt; replay does not create new evidence.
4. Real CPU/memory/disk telemetry authenticated with the same current version/job/runtime, increasing sample sequence and received after activation; sample acquired after daemon start, no fabricated defaults. Receipt age <=60s and heartbeat age <=45s at verification; client sample time skew <=60s and valid metric bounds. Server receipt ordering is primary evidence, not client timestamp.
5. Requested agent artifact digest/version/config hash and telemetry-only mode match. Docker remains independently disabled unless previously explicitly authorized; install does not grant it.

Restart/upgrade/re-enroll/rotate require a new runtime instance; INSTALL a new managed runtime. DIAGNOSE can use the current persistent instance but requires a new challenge/receipts after its diagnostic action; never relies on historical ONLINE. Old agents without proof remain monitored normally but cannot satisfy managed provisioning success. Success is historical evidence at a time, not a guarantee that a host remains ONLINE forever.

Challenge is a bearer proof under trusted manager/OS permissions, not cryptographic PID attestation; a malicious root/administrator can impersonate the service. Document this trust boundary, do not advertise hardware assurance.

## 8. OS lifecycle and rollback

### Linux

Ubuntu 24.04 x64 + systemd initial support. Root-owned versioned releases `/opt/nimbusops-agent/releases/<digest>`; configuration `/etc/nimbusops-agent/config.v1.json`; state/journal `/var/lib/nimbusops-agent`; logs via sanitized journald. Dedicated nonlogin telemetry account, state directory 0700 and secret files 0600 owned only by intended service/manager; protect parent directories and reject symlink/path traversal. Privileged fixed manager root-owned, daemon unprivileged. Unit has explicit absolute executable/config paths, Restart=on-failure with bounded start rate, SIGTERM grace 30s, install WantedBy multi-user.target, and compatible hardening. Do not add Docker group or socket mounts during provisioning.

Installer verifies manifest/digest against trusted release metadata, stages offline-pinned dependencies/runtime before cutover, validates config, locks journal, stops old service, switches version/config atomically, starts and records activation. Install twice reconciles same service/identity. Existing unmanaged files/service conflict blocks rather than overwrites. Uninstallation/data removal is not a Sprint 5 operation.

### Windows

Recommended supported persistence: **WinSW service**, not Task Scheduler, with exact vetted wrapper version and digest in release manifest. Actual wrapper version/digest and redistribution/license review must be approved before implementation packaging. Windows Server 2022 x64 and a pinned supported Python runtime are proposed initial matrix. Use `C:\Program Files\NimbusOps\Agent\releases\<digest>` and `C:\ProgramData\NimbusOps\Agent\{config,state,journal}`. SCM service automatic delayed start, bounded recovery/backoff, graceful stop and startup health; no user-login dependency or PowerShell execution-policy bypass as runtime mechanism.

Use a dedicated virtual service account where supported by vetted wrapper; local privileged manager runs separately with explicit operator authorization. Directory ACLs grant only SYSTEM, Administrators and intended service SID; remove inherited broad grants, verify effective access, reject reparse points and writable executable/config parents **before** writing secrets. ACL failure is fatal, never swallowed. Confirm service-account/wrapper compatibility in disposable Windows tests; if unsupported, return setup-required rather than silently switch to LocalSystem or Task Scheduler. Config/identity writes use atomic replace under a named OS mutex and explicit ACL recheck. Service install/change, not ordinary monitoring, requires elevation.

### Upgrade / rollback common rules

Config schema_version=1, strict validation, current and last-known-good **nonsecret** config; separate secret state from release directories. Stop daemon and drain/quarantine conflicting Docker work, stage new release, atomic activation, construct new Sender, verify; preserve stable host ID. Reverting runtime/config is allowed only if it understands the current identity/protocol and does not resurrect revoked/grace credentials. Never roll back identity or restore stale control-plane DB over newer credentials. Unknown commit state blocks rollback requiring a credential assumption. Disk full/partial copy/service failure retains journal and protected candidate; reports exact safe remediation without exposing material.

Reboot testing is mandatory for install/upgrade/credential handoff, including reboot after server commit but before local activation. Existing valid daemon may remain running only for pre-cutover staging failures with no identity mutation. After identity commit, use current pending identity or stop safely; old-token restoration is prohibited.

## 9. API and authorization contracts

Additive `/api/v1` routes, snake_case JSON, strict unknown-field rejection. Preserve legacy route errors/envelopes. New routes use RFC 9457 problem details with stable type URI, code, request_id, safe detail, retryable, remediation; no provider exception details. UUID resources are not bearer secrets. Contract companion: `2026-11-17-sprint5-openapi.json` (OpenAPI 3.1; JSON is an accepted OpenAPI serialization).

| Method and relative path | Authority / result |
|---|---|
| GET `/provisioning/providers` | ADMIN; provider/connection setup state, support and remediation, paged |
| GET `/provider-connections/{connection_id}/targets` | ADMIN + connection scope; paged discovered descriptors, no execution |
| POST `/provisioning-validations` | ADMIN + CSRF/origin; target/operation/config → 201 immutable review + expiry and explicit privilege list |
| GET `/provisioning-validations/{validation_id}` | same ADMIN owner (or ADMIN review policy), no capability secret |
| POST `/provisioning-jobs` | ADMIN + CSRF/origin + Idempotency-Key; validation/fingerprint/confirmed=true → 202 + Location |
| GET `/provisioning-jobs` | ADMIN/VIEWER; paged sanitized history, state/provider/host filters |
| GET `/provisioning-jobs/{job_id}` | ADMIN/VIEWER; status, safe evidence, reason, allowed_actions; VIEWER strips provider internals/actor identifiers |
| GET `/provisioning-jobs/{job_id}/events` | ADMIN/VIEWER; after_sequence exclusive cursor, limit<=100; increasing sequence, no raw logs |
| POST `/provisioning-jobs/{job_id}/cancellation` | ADMIN + CSRF/origin; singleton idempotent intent; 202 until settled, terminal409 |
| POST `/provisioning-jobs/{job_id}/retries` | ADMIN + CSRF/origin + Idempotency-Key; fresh validation/review, safe terminal parent → 202 new job |
| POST `/agents/provisioning-grants` | independently authenticated configured VM workload identity only; dispatch/target binding → ephemeral grant body; never operator session or agent bearer |
| POST `/agents/managed-enrollments` | single-use scoped capability bearer; proposed credential + candidate binding → safe commit metadata |
| GET `/agents/managed-enrollments/{commit_id}` | current agent credential + X-Host-Id, only own host/commit; safe current/invalidated status, no secret |

Manager control (SSH/pipe/status/challenge delivery) is a fixed provider protocol, not an arbitrary public HTTP manager endpoint. Existing `/agents/heartbeat` and `/agents/telemetry` get optional managed proof fields; absent fields preserve old monitoring. Internal grant issuance for SSH/pipe is not browser-accessible.

Authentication matrix: anonymous denied401; VIEWER read-only sanitized job/event history, denied provider inventory/validation/mutations403; ADMIN may request only server-policy-authorized targets, cannot upload keys/grant RBAC through these endpoints; worker uses process identity and DB leases, not an operator session to impersonate approval; manager uses connection authority for its one target; grant can only enroll its dispatch; agent bearer can only heartbeat/telemetry/own commit status. All cookie-authenticated mutations retain established session + origin/CSRF guards. Workload/grant bearer routes explicitly reject cookie auth as a substitute.

Lists use opaque integrity-protected cursors bound to filters, limit default20/max100. Jobs sort `(created_at,id)` descending; targets `(canonical_key,id)`; provider list `(id)`; events by sequence ascending. Cursors contain no credential/provider secrets and expired/invalid cursor →400. Discovery cursor follows bounded provider paging but is wrapped server-side. Query filters: state (seven-state enum), provider, host_id; unknown filters rejected. 404 conceals out-of-scope resources. Cache-Control:no-store on authenticated responses; no credential in URL, browser storage, analytics or referrer. Only job ID/filter/cursor may persist in URL.

Proposed limits: 10 job creates/min/ADMIN, 20 validations/min/ADMIN, discovery 10/min/connection, 60 read requests/min/session (events poll minimum2s; backoff to10s when unchanged); 429 Retry-After. Global active jobs20; execution concurrency separately bounded in §1. Enforce server-side with durable/global counters or single-node shared limiter, not per-web-process memory. Grant exchange limit 5/min/dispatch and strict TTL; trusted-identity failures do not reveal target existence.

Errors: 400 malformed cursor/header;401 missing/invalid auth;403 role/provider authorization;404 unknown/out-of-scope resource;409 key mismatch/ownership/state/version/identity conflict;410 unconsumed validation/grant expired;422 unsupported config/OS;429 rate/queue limit;503 setup/provider/DB busy;500 internal error with request_id. Every non-2xx uses Problem (including request validation on new routes). Retry-After for429/503. An external failure after acceptance appears as durable job outcome, not an HTTP create failure that encourages duplicate submission.

Example create body: `{"validation_id":"<uuid>","approval_fingerprint":"<64hex>","confirmed":true}` with `Idempotency-Key: <random nonsecret key>`. Config/target are loaded from immutable validation, not accepted again at create. Example safe job: `{"id":"<uuid>","state":"RUNNING","step":"RECONCILE_REMOTE","reconciliation_required":true,"reason_code":"PROVIDER_OPERATION_UNKNOWN","allowed_actions":["REQUEST_CANCEL"],"host_id":null}`.

API evolution: new additive routes/optional proof in v1; no existing field meaning changes. Breaking managed protocol revisions negotiate explicit `protocol_version`; unsupported version fails422, never falls back to legacy enrollment. Full generated-contract tests and mock exercise are implementation entry gates; design validation result is recorded separately, not presumed.

## 10. Dashboard behavior (functional specification, no UI implementation)

Preserve current visual identity and session routing. Add Server becomes a real wizard, with existing operator-assisted enrollment distinctly labeled, not represented as zero-touch. No import of active UX WIP by implication.

1. **Provider/environment:** explain LOCAL_WINDOWS execution location; show setup-required and support matrix. Environment is metadata, not authority. Do not expose secrets or a credential entry form.
2. **Target selection:** bounded discovered list; identity summary and connection scope; loading, empty, permission denied and unavailable states distinct. No arbitrary IP scan. Existing host mapping visible, recovery separate from INSTALL.
3. **Configure:** pinned allowed artifact/mode/environment; Docker default unchanged. Unsupported version/OS disabled with explanation.
4. **Validate/review:** server-produced check results and exact target/host, install version/digest, service account, paths, privileges and destructive/non-destructive effects. Expiry/change invalidates review. Explicit confirm; no install during validation.
5. **Submit/progress:** disable duplicate button locally but rely on server idempotency; persist nonsecret idempotency key only for safe request replay. Timeline from durable events, actual step state/timestamps; indeterminate progress, no fabricated percentages. Distinguish waiting for worker, running remotely, verifying, reconciling and awaiting operator action.
6. **Completion:** host link only after verified identity; “installed but verification failed” is not success. Show heartbeat evidence receipt time and current live connectivity separately. Cancellation may leave installed files or new valid identity; disclose effects.

Page refresh resumes by job ID with current auth; closing wizard does not cancel. Network loss displays “progress unavailable” and last refresh time while job continues. Session expiry prompts login and preserves only nonsecret route/job information. History filters/page cursor and host detail recovery actions use allowed_actions computed by server (UI gating is not authorization). Retry reopens review with a fresh validation, never reuses an expired approval. Cancel dialog explains cooperative/uncertain semantics; no force action. Disabled actions have reasons; do not render enabled decorative controls.

Accessibility acceptance: semantic headings and ordered step list, programmatic labels, keyboard-only navigation, focus moved to error summary/next heading, focus trap/return for dialogs, aria-live polite for changed stage (not every poll), noncolor status text, reduced-motion support and visible focus. Unit/contract tests plus real browser keyboard/accessibility checks required. No raw HTML rendering of provider diagnostics, client-generated success or secrets in storage/URLs/logging.

## 11. Failure, cancellation and recovery runbooks

| Situation | Required behavior |
|---|---|
| Worker crashes before intent | claim after lease; no external effects; revalidate approval |
| Crash after intent / remote acceptance before handle commit | reconcile predetermined correlation + journal; UNKNOWN blocks redispatch |
| Grant lost before enrollment | prove no commit, invalidate old unconsumed grant and renew through independent channel; no consumed-grant retry with a different candidate |
| Enrollment committed / response lost | same candidate request returns safe commit metadata; status confirms current; retain pending candidate |
| Host revoked while job runs | revoke wins auth, invalidate grant/challenge, block steps; reconcile existing action; never un-revoke with old intent |
| Daemon not restarted / old Sender continues | old-generation/grace evidence cannot pass; restart through authorized manager, no helper heartbeat substitution |
| Offline/revoked host, no management | setup-required operator-assisted bootstrap; no agent-token bypass |
| Artifact/ACL/disk/service error | fail closed before secret write/cutover where possible; keep journal and valid current identity; safe partial-effect diagnostics |
| Cancel during mutation | persist intent; manager stops only at safe boundaries; read status until proven stopped/finished; keep ownership while unknown |
| Deadline reached with uncertain effect | stop new mutations, retain nonterminal reconciliation state/ownership, alert operator; no scheduled duplicate retry |
| Competing manual lifecycle/Docker change | guarded transaction denies conflict except immediate security revoke; preserve monitoring and history |

No automatic “release ownership” operator button. Resolution uses authenticated independent channel and fixed status reconciliation; if that channel is unavailable, retain lock and show setup steps. Future manual adjudication requires separately specified evidence/audit and approval, not a JSON assertion that an operation stopped.

Metrics/alerts: queue age, lease churn, DB busy, unknown outcomes, reconciliation age, grant expiry, verification failures, cancellation age; IDs and safe codes only. Default unresolved alert after5min, no destructive auto-remediation. Structured events allow audit of requester/reviewer/config scope and actual transitions; restrict detailed operator audit to ADMIN. Logs allowlist fields rather than relying only on redaction. Secret-canary tests cover proxy, SDK, OS process arguments, service config and browser storage.

## 12. Dependency-aware TDD work packages (not an execution authorization)

Each package: reproduce failing behavior/test (RED), minimal implementation (GREEN), refactor, targeted tests, complete relevant regression, small scoped commit, independent review. Separate writing branches/worktrees if delegation is later approved; this design has only a read-only builder reviewer. A detailed executable implementation plan follows design approval, using writing-plans; no implementation skill/code now.

| ID | Package / likely files | Depends on | First failing tests / exit evidence |
|---|---|---|---|
| D0 | Resolve enablement decisions; freeze/lint OpenAPI and threat/protocol review | design approval | Contract examples validate; wrong-role/grant boundaries explicit; no implementation until plan approval |
| D1 | New models/migration/readiness in `backend/app/models`, `core/migrations.py` | D0 | Upgrade/repeat/rollback-copy tests, required-index fail-closed, populated legacy DB unchanged |
| D2 | Provisioning service/API/auth/idempotency/ownership | D1 | concurrent same key/same job, mismatch409, all auth/CSRF/scope cases, revoke-vs-job/Docker races |
| D3 | Separate worker/leases/intents/reconciliation/cancel | D2 | killed process at every boundary, lease/ownership fences, no double execution, fake clock/backoff/deadlines |
| D4 | Managed enrollment/auth context/receipts/challenges | D2 | atomic grant+host commit, duplicate candidate, response loss, revoked/grace/stale/wrong host/runtime/replayed proof denied |
| D5 | Agent pending journal/stop-start/credential permissions | D4 | no old credential rollback; Sender reconstructed; reboot pending recovery; ACL/mode failures; helper not accepted |
| D6L | Linux manager/SSH/systemd packaging | D3,D5 | stdin secrecy, host key pin, journal dedup; separately approved real Ubuntu double install/reboot/upgrade/stop |
| D6W | Windows manager/pipe/WinSW packaging | D3,D5, wrapper decision | pipe ACL/peer identity, SID ACL fail-closed, reparse protection; approved disposable Windows reboot/upgrade |
| D7 | Azure discovery/RBAC/Managed Run Command/identity exchange | D3,D4,D5, relevant OS package | mocked scope/SDK no-retry/unknown tests, JWKS audience/principal/target binding; separate approved Azure tests |
| D8 | Wizard/progress/history in `frontend/src/views` and typed client | stable D2/D4 contracts | API mock state cases, no token storage, retry/cancel truthful, keyboard browser flow; then real loopback slice |
| D9 | Recovery/upgrade integration and independent review | D6L/D6W/D7,D8 | revoked/offline restore uses separate channel, stable IDs, Docker quarantine, rollback credential safety |
| D10 | Full regression/failure injection/release evidence | all scoped packages | pin revision/toolchain; backend+agent+integration+frontend/build/browser, real OS/Azure gates distinct |

Do not serialize unrelated OS/frontend work unnecessarily, but schema/API ownership must be stable before parallel writers. Proposed first vertical slice: Generic Linux authorized SSH → install → managed enrollment → persistent heartbeat → dashboard timeline; Azure/Windows stay setup-required until their enablement gates pass. This ordering is a recommendation, not reduced sprint scope.

## 13. Acceptance ledger and rollback strategy

| Acceptance | Required evidence class |
|---|---|
| Seven-state transitions/events atomic; leases restart safely | unit, SQLite concurrent process and kill-point tests |
| Uncertain acceptance never causes duplicate external execution | fake adapter call count + process crash tests; real provider correlation/journal gate |
| No false success from old ONLINE, telemetry-only last_seen, GRACE/wrong generation, stale sample, helper, replay or revoked host | API/agent loopback integration with actual token comparison and runtime receipts |
| Stable identity and safe handoff across lost response, crash, reboot and re-enroll | integration + disposable real OS; old revoked token denied throughout |
| Permission boundaries, CSRF, target scope, nonsecret errors and logs | API/security contract tests; canaries in all logging/argv/browser channels |
| Linux persistent install/stop/upgrade/rollback, install twice | real Ubuntu 24.04 systemd + reboot, not mocks |
| Windows startup independent of login, verified SID ACLs, graceful stop/upgrade/rollback | real Windows Server 2022 + reboot; mocks insufficient |
| Azure existing scoped VM only, denial and missing identity truthful, no VM/network create/delete permissions | mocked SDK + separately approved real Azure allowed/denied targets |
| Wizard/history/recovery functional, reload/disconnect truthful, keyboard accessible | frontend tests, browser flow and loopback service; no simulated success |
| Existing auth/telemetry/Docker/host identity contracts preserved | full immutable-revision baseline regression and migration fixture comparisons |

Rollback order: disable new submission and dispatch via server configuration; continue read/status/reconciliation; stop worker only after recording/quiescing known actions (remote commands may outlive it); retain jobs/events/grants/ownership and valid credential state; roll back release/config only to a compatible binary; restart monitoring and verify current credential. Additive tables remain, no automatic down migration or stale DB restore. If old baseline cannot honor new credential/revocation/ownership invariants, it is not a safe rollback binary: use a tested forward-fix/compatible maintenance release with dispatch disabled. Before schema work, backup/restore rehearsal must establish recovery-point implications and identity reconciliation. No container/data/VM/network destruction, no credential downgrade.

Code-green is not release approval. Separate operator approval required for disposable OS privileged tests, Azure tests, packaging distribution, production migration, deployment or rollout. Sprint4 outstanding release gates remain outside this design authorization.

## 14. Decisions still requiring approval or evidence

The core engine and protocols above are specified for implementation planning. A fully enabled provider cannot honestly be called ready until these gates close:

| Gate | Recommended decision / evidence needed | Blocking scope |
|---|---|---|
| G1 LOCAL_WINDOWS location | Local control-plane Windows worker + pre-established privileged pipe manager; not browser PC/remote arbitrary host | local Windows adapter |
| G2 GENERIC_LINUX authority | SSH pinned identity + preinstalled restricted manager/sudo contract; choose approved connection owners/endpoints | Linux provider |
| G3 Windows persistence | Vetted pinned WinSW release/license/hash, virtual-service-account compatibility and exact runtime packaging | Windows installation/upgrade |
| G4 Azure bootstrap identity | Existing system-assigned VM identity + dedicated bootstrap audience/tenant config; approve trust/claim validation; no identity assignment in sprint | Azure enrollment |
| G5 Azure provider contract | Pin SDK/API version, validate custom role action names/LRO permissions and real named-command lost-response behavior; safe argv/log/extension-output test | Azure dispatch enablement |
| G6 Packaging/support | Approve Ubuntu24.04 x64, Windows Server2022 x64, pinned artifact/runtime/dependency manifest and trusted distribution owner | real OS certification |
| G7 Test and deployment targets | Explicit disposable hosts/subscription/RG/VM allowlist, privileges/budget and test window | real OS/Azure tests; never inferred from design approval |

Absent a gate, adapter reports setup-required with actionable instructions; it does not pretend to provision. Designer defaults (timeouts/concurrency/TTL/retention, supported OS and first vertical slice) need confirmation with the design, not live changes now.

## 15. Normative protocol clarifications after independent review

This section takes precedence over abbreviated earlier descriptions. These are designer resolutions within the approved safety requirements, not claims about existing code.

### 15.1 Irrevocable attempt closure and late senders

Add `closed_at`, `closure_reason` and `admission_state` (OPEN/ADMITTED/CLOSED) to attempts. Admission is a DB CAS on the exact dispatch ID, intent hash, job revision, ownership generation, revocation_revision and cancellation state. The manager must obtain admission immediately before the first privileged effect; admission is valid for only that journaled dispatch, never for another ordinal. A worker's local permission check is not admission.

A reconciler MUST close OPEN admission transactionally **before** treating a definitive negative lookup as safe to retry. CLOSED never reopens. If admission raced and became ADMITTED, closure/ownership release/retry is forbidden until the manager proves that dispatch terminal. If closure wins, any delayed worker call must be rejected by manager admission even if it subsequently reaches the target. Unknown or unqueryable admission/manager state retains ownership. On manager crash after admission but before effect, journal reconciliation owns the resolution; no second manager instance starts the effect. Cancellation/revocation closes OPEN attempts; ADMITTED work is stopped at safe boundaries and reconciled. A new ordinal gets a new dispatch ID only after prior closure/terminal effect is established.

### 15.2 Revocation revision

Add `hosts.revocation_revision INTEGER NOT NULL DEFAULT 0` additively; every explicit ADMIN revoke increments it, including repeated revokes of an already revoked host. Review, grant, target binding and credential commit store `expected_revocation_revision`. Revoke and admission/enrollment/success predicates serialize under SQLite write transactions. An explicitly approved REENROLL may clear only the revoked state at the exact reviewed revision. Revoke before grant/admission/commit invalidates that authority; revoke after commit immediately denies the new credential and invalidates challenges. Recovery never decrements revision. `expected_credential_version` independently prevents concurrent rotation overwrite. INSTALL has no existing host revision until atomic host mapping; any competing existing identity causes conflict, not replacement.

### 15.3 Global machine/installation ownership

Add `provisioning_machines(id UUID PK, machine_binding_hash UNIQUE, installation_id UNIQUE nullable, binding_revision)` and target.machine_id FK. Ownership is keyed by machine_id (not connection-specific target_id), with target/host as references. Preflight must query the same root-owned manager identity/journal through every channel: fixed machine binding, installation UUID and shared lock/journal namespace. A signed/independently authenticated manager receipt binds channel identity to machine binding; an unverified client report is not sufficient. If there is no manager yet, the fixed read-only bootstrap probe obtains OS machine identity through the authorized channel; ambiguous/cloned identity blocks dispatch until explicit mapping. No privileged install is admitted without a resolved machine row.

Azure/local/SSH aliases resolving to the same binding join one machine row; conflicting Azure vmId/SSH pin/installation IDs block. All installers use `/var/lib/nimbusops-agent/manager` or `ProgramData\\NimbusOps\\Agent\\manager` for the same OS lock/journal, regardless of provider. A second INSTALL encountering any managed installation returns ALREADY_MANAGED without replacing identity, even after a prior job finished. Operator-assisted mapping uses protected server configuration: disable dispatch, obtain read-only receipts through both authorized channels, review exact host/installation identity, apply versioned mapping by a fixed ADMIN maintenance command under the same DB ownership guard, audit and revalidate. No arbitrary DB edit or public alias-merge endpoint. Its implementation/tests belong in D2; a missing mapping workflow yields setup-required.

### 15.4 Manager protocol v1

The following are fixed framed messages over SSH stdin or ACL/peer-checked pipe, or fixed Azure guest-manager HTTPS exchanges. All requests carry protocol_version=1, job_id, dispatch_id, intent_hash, machine binding, ownership generation, expected credential/revocation revisions, request_id and monotonic journal sequence. Responses echo binding and durable journal sequence. Target IDs alone never authenticate them.

| Message | Authority and durable effect |
|---|---|
| STATUS | independent connection identity; read journal/OS lock/supervisor state, never mutate |
| ADMIT | exact current OPEN attempt; backend atomic OPEN→ADMITTED, return safe admission receipt; replay same dispatch returns same receipt |
| START_ACTION | independent channel + admitted receipt; manager fsyncs admission receipt before fixed action; duplicate dispatch returns existing journal status |
| CONFIRM_ACTIVATION | manager reads supervisor PID/start time/service identity and creates runtime_instance_id itself; backend persists activation idempotently by (dispatch_id, supervisor start identity), increments activation epoch; new activation invalidates older challenges |
| ARM_CHALLENGE | backend produces fresh nonce after activation; manager writes only to protected daemon state; no helper-selected runtime ID; hash, expiry, activation epoch and receipt watermark durable server-side |
| CANCEL | exact bound intent; cooperative stop request; terminal confirmation includes OS lock/process/journal evidence |
| CLOSE_RESULT | fixed sanitized terminal receipt; backend fences acceptance, journal retains result even if response lost |

SSH/pipe worker relays receipts only after authenticating the target peer. For Azure, manager HTTP messages require the same independently validated VM workload identity as grant exchange, plus exact dispatch/machine binding; implement under a separate manager-auth router, NOT agent bearer or operator cookie. Its schemas/auth/negative tests must be frozen in D0 before code; these internal exchanges are normative even though the public OpenAPI companion does not enumerate manager transport RPCs. No generic message payload/script field is permitted.

Successor queries STATUS over the independent channel and matches stored activation/journal receipt; it cannot trust an old worker's uncommitted assertion. Runtime challenge handling is recoverable: consumed proof remains a durable receipt; if receipt becomes stale before verification completes, re-arm a new challenge for the **same supervisor-confirmed live runtime**, invalidating the prior nonce but retaining its audit. Only one active challenge per job/activation epoch; repeated challenge delivery is safe. Runtime restart requires a new activation epoch/instance and new receipts. Daemon heartbeat reads protected challenge state; helper/CLI has no qualifying receipt path. D0 includes golden request/receipt fixtures for every message and crash/replay/closed-attempt tests.

### 15.5 Approval continuation

Approval expiry governs **initial ADMIT of a new dispatch**. Admission before expiry durably authorizes only the enumerated steps in that approved intent: artifact staging, credential candidate preparation/commit, service stop/switch/start and verification/challenge refresh within the admitted remote-action deadline. It does not authorize a new dispatch/ordinal, artifact/config change or second credential commit. Managed enrollment checks the unrevoked admitted authorization snapshot, exact revisions and action deadline, not the expired wall-clock approval itself. Existing non-admitted work stops at expiry. Security revocation/cancellation still blocks new privileged steps; after a credential commit, preserve the current identity and perform safe stop/reconciliation rather than credential rollback. Read/status/evidence collection can continue beyond deadlines. If a deadline expires between commit and activation, no automatic new restart dispatch is allowed; retain pending valid credential/journal and request a freshly reviewed recovery job after effects resolve.

### 15.6 Contract corrections and authoritative Azure binding

Config requested mode is TELEMETRY_ONLY for INSTALL; for lifecycle it is PRESERVE, resolved by server into effective mode TELEMETRY_ONLY or EXECUTOR from existing separately authorized state. Immutable review includes effective_mode and effective config hash. Mode is never an instruction to grant Docker. Environment remains exactly baseline PRIVATE/PUBLIC-CLOUD; no LAB enum expansion.

Commit status with current credential returns `current=true` only when that commit version/hash is still current. An authenticated newer current credential of the same host may query an older commit and receive `current=false`; stale/grace/revoked credentials receive401 and no safe-promotion assertion. Replayed enrollment metadata has `current` calculated at read time and may be false; caller MUST also use current credential status before promotion. Unknown network status is not false/safe rollback.

Azure binding must be refreshed by authoritative ARM read at validation, immediately before dispatch admission and on **every** workload exchange/manager message authorizing mutation: exact tenant, system-assigned principalId, vmId and normalized resource ID must equal approved snapshot. Cache is permitted only for read-only status (<=30s), never mutation authorization; ARM/JWKS unavailability fails closed. Validate signed trusted tenant claims, configured issuer/audience/time and `oid`/tenant binding; reject non-workload token types and missing/ambiguous claims. If tenant cannot distinguish the intended token class, adapter remains disabled pending reviewed policy. Identity/VM recreation invalidates mapping/review/grants, even if hostname/ARM path unchanged. Shared user-assigned identities are rejected.

Replacement grant issuance requires authenticated manager STATUS receipt binding same candidate_id/hash and dispatch to PREPARED with no committed result, DB proof that no grant/candidate commit exists, and transactional revocation of old unconsumed grant. Enrollment and replacement serialize on the same attempt/grant row; a delayed old-grant request either commits first (replacement returns commit status) or is rejected after revocation. A missing/uncertain journal or prior admission does not prove no enrollment: reconcile, never mint blindly. Lost response after a committed enrollment uses the persisted candidate and same-grant safe metadata replay, not replacement. These bindings/denials are mock-testable before real Azure enablement.

## Design-work checklist

- [x] Read selected approach, global architecture playbook and baseline source; preserve active UX work.
- [x] Create isolated worktree/branch exactly at approved f3a8809.
- [x] Document architecture, state/schema/migration, APIs/auth, worker guarantees, providers, credentials/proof, OS lifecycle, UX, failures, TDD, rollback and acceptance.
- [x] Validate machine-readable API structure with available tooling; record missing standard lint/mock validation as D0 gate.
- [x] Fresh independent builder check; seven findings resolved in normative §15 and follow-up review found sufficient for design approval, not provider code-readiness.
- [x] Final structural/whitespace and documentation-only scope verification; documentation commit recorded in Git history.
- [ ] Operator approves full design and unresolved decisions.
- [ ] Detailed execution plan approval before any application implementation.
