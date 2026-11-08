# NimbusOps Security Model — Phase 1 (single-host monitoring)

Scope: the agent→server and browser→server trust boundaries implemented in
this phase. This is a minimal, defensible model — not an enterprise one.
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

- Agent endpoints (`heartbeat`, `telemetry`) require `X-Host-Id` +
  `Authorization: Bearer <agent-token>`.
- Wrong token → `401 UNAUTHORIZED`. Valid token for a different host →
  the token is simply not valid for that host (401). Unknown host → 404.
- Tokens are never logged; enrollment attempts are audited (hostname +
  outcome only, no token material).

## Transport security

- Local development on one machine: loopback HTTP is acceptable.
- Anything across machines/networks: the server must be behind HTTPS or a
  verified secure private tunnel (e.g. Tailscale). This implementation does
  not add TLS itself and does not silently downgrade: it is the operator's
  deployment responsibility, and the server should not be exposed otherwise.
- No inbound ports on managed hosts. The agent only makes outbound calls.

## Known limitations (accepted for Phase 1)

1. **No revocation/rotation workflow.** Re-enrollment rotates a token, but
   there is no API to revoke without re-enrolling. The `revoked_at`/
   `is_revoked` columns exist; the operator UI/API for them is Phase 5 work.
2. **No operator authentication.** Read endpoints are public to whoever can
   reach the server. Phase 1 assumes a trusted/traversable-only-by-team
   network. PRD v1.0 (RBAC) is out of scope here.
3. **Enrollment token is compared with `secrets.compare_digest` but is a
   shared static token**; it grants enrollment only, not agent data access.
4. **Hashes are fast keyed SHA-256, not Argon2** — appropriate for 256-bit
   random tokens (no brute-force incentive), not for human passwords.
5. **CORS** is an explicit allowlist (`NIMBUSOPS_CORS_ORIGINS`); `*` is
   rejected at startup. Credentials are not allowed cross-origin.
6. **No rate limiting** on auth endpoints yet; a misused endpoint could be
   spammed. Bounded by network exposure choices above.

## Verification performed (local, Windows dev host)

- Wrong/missing agent token → 401 (automated tests).
- Enrollment with wrong token → 401; with no configured token → 503 (tests).
- Public host payloads expose no token material (asserted in tests).
- Enrollment audit rows written for success and denial (DB, tests).
- CORS wildcard rejected at startup (unit-enforced by settings parse).
