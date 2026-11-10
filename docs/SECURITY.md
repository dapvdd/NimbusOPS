# NimbusOps Security Model — Phases 1–3B

Scope: the agent→server and browser→server trust boundaries implemented
through Phase 3B (secure enrollment). This is a minimal, defensible model —
not an enterprise one. Known limits are stated, not hidden.

## Trust model

```text
Browser (untrusted)  --HTTP-->  Control Server (trusted)  <--HTTP--  Agent (semi-trusted)
     |                               |                                     |
     +-- no credentials for agents   +-- SQLite (local file)               +-- holds its own agent token
```

- The **browser** is untrusted: reads stay public (trusted-local model);
  **all mutations require an operator session** (Phase 3B, AC-01). The
  session token lives in JavaScript memory only — never localStorage,
  sessionStorage, or cookies (REACT-AUTH-001, O1 accepted) — so it dies with
  the tab and cannot be exfiltrated by storage-reading XSS. Deployment must
  still restrict network reachability (loopback, LAN, or tunnel).
- The **agent** is semi-trusted: it can write only heartbeats and telemetry
  for its own host_id, and only with its credential. It cannot read other
  hosts, cannot enroll others, and cannot execute anything on the server.
- The **server** holds all state and never forwards credentials anywhere.

## Enrollment (bootstrap)

Phase 3B replaces the shared static token as the primary path (O2, O5):

- **Preferred (Phase 3B):** the operator (ADMIN) issues a **single-use
  bootstrap token** scoped to one hostname, TTL ≤ 1 h (default 10 min). The
  token is shown once in the dashboard (copy + expiry countdown) and stored
  only as a keyed SHA-256 hash. The agent presents it at
  `POST /api/v1/agents/enroll`; consumption is an atomic single-row UPDATE —
  replay → `409`, expired → `410`, revoked or wrong-hostname → `401`.
- **Legacy (transition, O5):** the shared `NIMBUSOPS_ENROLLMENT_TOKEN` still
  works through Phase 3B and is removed in Phase 4. The old silent
  un-revoke is gone: a REVOKED hostname requires the operator re-enroll flow.
- The server issues a per-agent credential (256-bit random,
  `secrets.token_urlsafe`), returns it exactly once, and stores only a keyed
  SHA-256 hash (pepper = `NIMBUSOPS_TOKEN_PEPPER` or, if unset, the
  enrollment token).
- Re-enrolling the same hostname via bootstrap rotates that host's agent
  token (old token stops working) while keeping the host's stable UUID.
  Restoring a REVOKED host also requires an operator-issued bootstrap token;
  the host is un-revoked only when an agent consumes it.
- With no enrollment token configured and no bootstrap presented,
  enrollment is disabled: `503 ENROLLMENT_DISABLED`. There is no
  unauthenticated registration.
- Simulated hostnames (`sim-*`) are rejected server-side
  (`400 SIMULATED_HOST_REJECTED`) — defense in depth alongside the
  browser-side guard.

## Operator authentication (Phase 3B — decision O1)

- The first operator is created out-of-band by script
  (`backend/scripts/create_operator.py`, prompts for a password ≥ 12 chars),
  never via an unauthenticated API.
- Login (`POST /api/v1/operators/login`) verifies the password with
  PBKDF2-SHA256 (240k iterations; a real KDF for human passwords — the fast
  keyed hash is used only for 256-bit random tokens) and issues a 256-bit
  session token, TTL 12 h (env-configurable). Generic "invalid credentials"
  for both unknown user and wrong password (no username enumeration).
- Sessions are stored **hashed** (keyed SHA-256); logout invalidates
  server-side; expiry is enforced at verification. Every mutation endpoint
  (bootstrap issue, host PATCH, rotate, revoke, re-enroll, deploy/start/stop)
  requires `role=ADMIN`; VIEWER receives `403 OPERATOR_FORBIDDEN`.
- The dashboard keeps the session token in memory only (never storage).
- All operator actions are audited to the append-only `host_events` table
  with the acting username (`BOOTSTRAP_ISSUED`, `CREDENTIAL_ROTATED`,
  `HOST_REVOKED`, `RE_ENROLL_REQUESTED`, `DOCKER_ENABLED/DISABLED`,
  `ENROLLED`, `RE_ENROLLED`).

## Agent authentication

- Agent endpoints (`heartbeat`, `telemetry`, `commands/poll`,
  `commands/{id}/result`) require `X-Host-Id` +
  `Authorization: Bearer <agent-token>`.
- Wrong token → `401 UNAUTHORIZED`. Valid token for a different host →
  the token is simply not valid for that host (401). Unknown host → 404.
  A result for another host's operation → 403 `FORBIDDEN_HOST`.
- Tokens are never logged; enrollment attempts are audited (hostname +
  outcome only, no token material).

## Transport security

- Local development on one machine: loopback HTTP is acceptable.
- Anything across machines/networks: the server must be behind HTTPS or a
  verified secure private tunnel (e.g. Tailscale). This implementation does
  not add TLS itself and does not silently downgrade: it is the operator's
  deployment responsibility, and the server should not be exposed otherwise.
- No inbound ports on managed hosts. The agent only makes outbound calls.

## Phase 2: Docker execution boundary

The agent executes Docker operations under these constraints (enforced in
`agent/nimbusops_agent/docker_exec.py`, tested in `agent/tests/`):

- **Optional by design.** Docker unavailability is a typed outcome
  (`DOCKER_UNAVAILABLE`); monitoring (heartbeat/telemetry) never depends on
  Docker.
- **Constrained invocation.** Only the Docker CLI, only fixed argv lists
  (`subprocess.run(shell=False)`), no shell string building, no docker SDK.
  The full argv of every command is predictable and auditable.
- **Managed-resource scoping.** Only containers whose name starts with
  `nimbusops-` may be started/stopped (`ManagedResourceError` otherwise).
  Created containers carry labels `nimbusops.managed=true` and
  `nimbusops.deployment=<id>`. No other container is ever inspected for
  lifecycle actions, and no prune/volume/network removal commands exist in
  the agent.
- **Allowlisted templates/images.** The agent double-checks upstream
  approval: only `nginx-demo` with image `nginx:1.27-alpine` executes;
  anything else → `UNAPPROVED_OPERATION` before Docker is touched.
- **No privilege escalation.** No `--privileged`, no host mounts (`-v`
  absent), no extra capabilities, `--restart no`, published port only.
- **No inbound access.** Commands arrive by authenticated outbound polling;
  results go out the same way. The Docker socket is never exposed over TCP
  by NimbusOps code.
- **Evidence before success.** `SUCCEEDED` is reported only after
  `docker ps` shows the container running (plus an HTTP probe recorded as
  `http_ok`). Timeouts/unverifiable outcomes → `UNKNOWN`.
- **Result validation.** The backend accepts only
  `SUCCEEDED|FAILED|UNKNOWN`, validates evidence shape, applies
  first-write-wins, and stores sanitized error messages (bounded length).

## Phase 3B: control-plane mutations (operator-gated)

- Application mutating endpoints (`/applications/deploy`, `/start`,
  `/stop`) now **require an operator ADMIN session** (`401` without,
  `403 OPERATOR_FORBIDDEN` for VIEWER) — closing the Phase 2 trusted-local
  gap (AC-01). Read endpoints remain public by design (Phase 3B scope).
- **Docker is default-off per host (O6):** a new/legacy-migrated host has
  `docker_enabled=false`; deploy/start/stop to it return
  `403 DOCKER_NOT_AUTHORIZED` and no operation row is created. An operator
  must explicitly enable Docker via `PATCH /hosts/{id}`; the agent also sees
  the flag in its heartbeat and refuses Docker ops client-side.
- Every mutation is still validated server-side: host must exist (404),
  template must be approved (422 `INVALID_TEMPLATE`), op types are an enum —
  no free-form command content is accepted from the browser.
- Duplicate protection is server-side and idempotent (an in-flight
  operation is returned, not re-created); repeated clicks cannot create
  uncontrolled deployments.
- Agent-facing commands are host-scoped and credential-gated; only the
  allowlisted op types (`DEPLOY`, `START`, `STOP`) ever reach an agent.
- **Claim-timeout recovery:** a RUNNING op past its claim deadline
  (`NIMBUSOPS_OP_CLAIM_TIMEOUT_SECONDS`, default 600) is re-queued by a
  background reconciler (+ lazy pre-poll check), so a crashed agent can no
  longer wedge a deployment; terminal ops are never touched.

## Known limitations (accepted through Phase 3B)

1. ~~**No revocation/rotation workflow.**~~ **Resolved in Phase 3B:** revoke
   (tombstone), rotate (grace window), and operator re-enroll are implemented
   (`/hosts/{id}` DELETE, `/rotate-credential`, `/re-enroll`).
2. ~~**No operator authentication.**~~ **Resolved in Phase 3B:** operator
   sessions (O1) gate every mutation; reads stay public (trusted-local).
   Restrict network exposure accordingly.
3. ~~**Enrollment token is a shared static token.**~~ **Resolved in Phase 3B:**
   single-use hostname-scoped bootstrap tokens are the primary path; the
   legacy shared token remains only as a transition shim (removed Phase 4).
4. **Hashes are fast keyed SHA-256 for tokens, PBKDF2 for passwords** —
   appropriate for 256-bit random tokens (no brute-force incentive); operator
   passwords use PBKDF2-SHA256 (240k iterations). Argon2id would be the next
   upgrade if operator count ever grows.
5. **CORS** is an explicit allowlist (`NIMBUSOPS_CORS_ORIGINS`); `*` is
   rejected at startup. Credentials are not allowed cross-origin.
6. **No rate limiting** on login/enroll endpoints yet; a misused endpoint
   could be spammed. Bounded by network exposure choices above. (Planned
   Phase 4.)
7. ~~**Operations claimed but never completed stay RUNNING.**~~ **Resolved in
   Phase 3B:** claim-timeout reconciliation re-queues ops past
   `NIMBUSOPS_OP_CLAIM_TIMEOUT_SECONDS` (default 600 s).
8. **Real-Docker verification not yet performed** (no Docker Engine on the
   development machine; see docs/PHASE2_VERIFICATION.md). The agent's
   Docker path is tested against a mocked runner only.
9. **Read endpoints remain unauthenticated** (Phase 3B scope decision): host
   inventory and metrics are readable by anyone who can reach the server.
   The operator-auth reads + HttpOnly cookie variant are Phase 5 (PRD RBAC)
   work, per the accepted architecture (O1 note).

## Verification performed (local, Windows dev host)

- Wrong/missing agent token → 401 (automated tests).
- Enrollment with wrong token → 401; with no configured token → 503 (tests).
- Public host payloads expose no token material (asserted in tests).
- Enrollment audit rows written for success and denial (DB, tests).
- CORS wildcard rejected at startup (unit-enforced by settings parse).
- Phase 2: unapproved template → 422 `INVALID_TEMPLATE`; unknown op type →
  `UNAPPROVED_OPERATION` before Docker is touched; non-`nimbusops-`
  container name rejected for start/stop (tests, mocked runner); command
  poll without token → 401; result for another host → 403 (tests).
- Fresh-context security review of the Phase 2 branch found no hardcoded
  secrets, no token disclosure paths, no wildcard CORS, no command
  execution surface (see docs/PHASE2_VERIFICATION.md).
