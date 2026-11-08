# NimbusOps Security Model — Phases 1–2

Scope: the agent→server and browser→server trust boundaries implemented in
these phases. This is a minimal, defensible model — not an enterprise one.
Known limits are stated, not hidden.

## Trust model

```text
Browser (untrusted)  --HTTP-->  Control Server (trusted)  <--HTTP--  Agent (semi-trusted)
     |                               |                                     |
     +-- no credentials for agents   +-- SQLite (local file)               +-- holds its own agent token
```

- The **browser** is untrusted: it can only read the public read endpoints.
  Phase 1 has no operator login; anyone who can reach the server can read
  host/metrics data. Deployment must therefore restrict network reachability
  (loopback, LAN, or tunnel) accordingly.
- The **agent** is semi-trusted: it can write only heartbeats and telemetry
  for its own host_id, and only with its credential. It cannot read other
  hosts, cannot enroll others, and cannot execute anything on the server.
- The **server** holds all state and never forwards credentials anywhere.

## Enrollment (bootstrap)

- The operator configures `NIMBUSOPS_ENROLLMENT_TOKEN` on the server.
- The agent presents that token once at `POST /api/v1/agents/enroll`.
- The server issues a per-agent token (256-bit random, `secrets.token_urlsafe`),
  returns it exactly once, and stores only a keyed SHA-256 hash (pepper =
  `NIMBUSOPS_TOKEN_PEPPER` or, if unset, the enrollment token).
- Re-enrolling the same hostname rotates that host's agent token (old token
  stops working) while keeping the host's stable UUID.
- With no enrollment token configured, enrollment is disabled: the endpoint
  returns `503 ENROLLMENT_DISABLED`. There is no unauthenticated registration.

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

## Phase 2: control-plane mutations (trusted-local model)

- Application mutating endpoints (`/applications/deploy`, `/start`,
  `/stop`) are **browser-initiated and unauthenticated in Phase 2**.
  This is a documented, deliberate limitation: the product is an academic
  MVP for a trusted local development environment. Deployment must
  restrict network reachability (loopback/LAN) accordingly. Operator
  authentication is Phase 5 (PRD RBAC).
- Every mutation is validated server-side: host must exist (404), template
  must be approved (422 `INVALID_TEMPLATE`), op types are an enum —
  no free-form command content is accepted from the browser.
- Duplicate protection is server-side and idempotent (an in-flight
  operation is returned, not re-created); repeated clicks cannot create
  uncontrolled deployments.
- Agent-facing commands are host-scoped and credential-gated; only the
  allowlisted op types (`DEPLOY`, `START`, `STOP`) ever reach an agent.

## Known limitations (accepted for Phases 1–2)

1. **No revocation/rotation workflow.** Re-enrollment rotates a token, but
   there is no API to revoke without re-enrolling. The `revoked_at`/
   `is_revoked` columns exist; the operator UI/API for them is Phase 5 work.
2. **No operator authentication.** Read endpoints AND application mutation
   endpoints are public to whoever can reach the server. Phases 1–2 assume
   a trusted local development environment. PRD v1.0 (RBAC) is out of
   scope here. Restrict network exposure accordingly.
3. **Enrollment token is compared with `secrets.compare_digest` but is a
   shared static token**; it grants enrollment only, not agent data access.
4. **Hashes are fast keyed SHA-256, not Argon2** — appropriate for 256-bit
   random tokens (no brute-force incentive), not for human passwords.
5. **CORS** is an explicit allowlist (`NIMBUSOPS_CORS_ORIGINS`); `*` is
   rejected at startup. Credentials are not allowed cross-origin.
6. **No rate limiting** on auth/mutation endpoints yet; a misused endpoint
   could be spammed. Bounded by network exposure choices above.
7. **Operations claimed but never completed stay RUNNING** until the agent
   reports (on reconnect the command is NOT re-delivered automatically in
   Phase 2 — a stuck RUNNING op requires a new deploy/start/stop request,
   which is idempotent-safe). Claim-timeout reconciliation is Phase 3 work
   per the PRD's retry/reconciliation criteria.
8. **Real-Docker verification not yet performed** (no Docker Engine on the
   development machine; see docs/PHASE2_VERIFICATION.md). The agent's
   Docker path is tested against a mocked runner only.

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
