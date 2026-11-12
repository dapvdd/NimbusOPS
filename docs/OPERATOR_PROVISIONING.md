# Operator Provisioning and Host Enrollment Guide

## 1. Provision an operator

Operators authenticate with username + password (PBKDF2-SHA256, 240k iters,
constant-time verify) and receive a bearer session token (12 h default TTL).

There is intentionally **no sign-up endpoint**. Seed the first operator with
direct DB access (see RELEASE_RUNBOOK.md §5), then manage everything in the UI.

Roles:
- `ADMIN` — mutations: deploy/start/stop/restart, enable Docker, rotate/revoke
  hosts, issue bootstrap tokens.
- `VIEWER` — read-only by server-side enforcement (403 on any mutation; pinned
  by tests).

Session lifecycle: `POST /api/v1/operators/login` → token; `POST /logout`
revokes; expiry enforced server-side. Login failures are rate limited
(5 / 300 s per username ⇒ 429 `RATE_LIMITED`).

## 2. Enroll a host (preferred: bootstrap token)

1. Log in as ADMIN → Operators view → issue bootstrap token (single-use,
   hostname-scoped, default TTL 600 s ≤ 1 h max).
2. Copy the token now — it is displayed exactly once (stored hashed).
3. On the host, run the agent with `NIMBUSOPS_ENROLLMENT_TOKEN=<bootstrap token>`
   and `NIMBUSOPS_SERVER_URL` pointing at the control plane.
4. The agent enrolls, receives a 256-bit agent token (shown once, stored hashed
   server-side), persists identity to `~/.nimbusops/agent.json`, and starts
   heartbeating.

Properties (pinned by tests):
- Redemption is atomic: 32 concurrent redemptions ⇒ exactly one 200 + 31×409.
- Expired/revoked/consumed tokens are rejected with stable error codes.
- A REVOKED hostname can only return via operator-issued bootstrap (never by
  re-presenting the legacy token).

## 3. Legacy shared-token path (transition only)

If `NIMBUSOPS_ENROLLMENT_TOKEN` is set on the server, agents may still enroll
with it. This path is accepted for the Phase 3B→4 transition and is disabled
outright when the variable is empty (recommended for production).

## 4. Credential rotation / revocation (ADMIN)

- Rotate: `POST /api/v1/hosts/{id}/rotate-credential` — the old token keeps
  working during the grace window (`NIMBUSOPS_CREDENTIAL_ROTATION_GRACE_SECONDS`,
  default 300 s) so the agent can be restarted without downtime.
- Revoke: `POST /api/v1/hosts/{id}/revoke` — heartbeat/telemetry/poll all
  reject with `HOST_REVOKED`.

## 5. Enabling Docker (per host, default OFF)

New hosts have `docker_enabled=false`. An ADMIN must explicitly enable it
(PATCH host or UI control). Until then every Docker-touching operation is
rejected server-side with 403 `DOCKER_NOT_AUTHORIZED` — the agent enforces the
same gate independently.
