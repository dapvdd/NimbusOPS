# Phase 3B API Contract — Secure Enrollment & Host Lifecycle

**Status:** DESIGN — NOT IMPLEMENTED.
**Date:** 2026-11-10 · Branch: `feat/phase3b-secure-enrollment`
**Conventions:** follows `docs/API.md` (Phase 1–2 contract); all endpoints under `/api/v1`; timestamps UTC ISO-8601; errors use the existing `{"error": {"code", "message"}}` shape (`core/errors.py`).

---

## 1. New Error Codes

Added to `core/codes.py` `ErrorCode` enum:

| Code | HTTP | Meaning |
|---|---|---|
| `OPERATOR_AUTH_REQUIRED` | 401 | No operator session/token on a protected endpoint |
| `OPERATOR_FORBIDDEN` | 403 | Authenticated operator lacks required role |
| `BOOTSTRAP_TOKEN_EXPIRED` | 410 | Bootstrap token past `expires_at` |
| `BOOTSTRAP_TOKEN_CONSUMED` | 409 | Bootstrap token already used (single-use) |
| `BOOTSTRAP_TOKEN_INVALID` | 401 | Unknown bootstrap token |
| `DOCKER_NOT_AUTHORIZED` | 403 | Host `docker_enabled=false` for a Docker op |
| `HOST_REVOKED` | 403 | Host is revoked; only re-enrollment via bootstrap possible |
| `SIMULATED_HOST_REJECTED` | 400 | `sim-` identifier rejected server-side |

---

## 2. Operator Authentication (new namespace `/api/v1/operators`)

### 2.1 POST `/api/v1/operators/login`

```json
Request:  {"username": "op", "password": "..."}
Response: 200 {"session_token": "<bearer>", "expires_at": "...", "operator_id": "..."}
```

- Session token: 256-bit random, stored hashed (`operator_sessions` table), TTL default 12h (env-configurable).
- Cookie variant (optional, for browser): `HttpOnly; SameSite=Strict; Secure` when TLS active.
- CSRF token returned alongside for cookie-based flows; not required for Bearer.

### 2.2 POST `/api/v1/operators/logout`

Requires Bearer session. Invalidates the session row. Idempotent.

### 2.3 GET `/api/v1/operators/me`

Returns `{"operator_id", "username", "role"}` for the active session.

**Operator roles (Phase 3B scope):** `ADMIN` (full control) and `VIEWER` (read-only). Role stored on the operator row; enforcement on all mutation endpoints.

---

## 3. Bootstrap Token Management (operator namespace)

### 3.1 POST `/api/v1/operators/bootstrap-tokens`

**Auth:** operator `ADMIN`.

```json
Request:  {"hostname": "david-lab", "expires_in_seconds": 600}
Response: 201 {
  "id": "<uuid>",
  "hostname": "david-lab",
  "token": "<shown once, never logged>",
  "expires_at": "...",
  "created_at": "..."
}
```

- `token` is returned exactly once in the response body and never stored in plaintext.
- `hostname` is required — the token is scoped to that hostname.
- `expires_in_seconds` default 600, max 3600.

### 3.2 GET `/api/v1/operators/bootstrap-tokens`

Returns list of bootstrap tokens (no token material): `id, hostname, created_at, expires_at, consumed_at, consumed_by_host_id, revoked_at`.

### 3.3 DELETE `/api/v1/operators/bootstrap-tokens/{id}`

Revokes (marks `revoked_at`) an unconsumed token. Idempotent. Consumed tokens cannot be revoked (already used).

---

## 4. Host Lifecycle Endpoints (operator namespace)

### 4.1 PATCH `/api/v1/hosts/{host_id}`

**Auth:** operator `ADMIN`.

```json
Request:  {"docker_enabled": true}
Response: 200 {"id", "hostname", "enrollment_status", "docker_enabled", "is_revoked", ...}
```

Allowed fields: `docker_enabled` (bool). `enrollment_status` and `is_revoked` are not directly settable via this endpoint (use revoke/re-enroll).

### 4.2 POST `/api/v1/hosts/{host_id}/rotate-credential`

**Auth:** operator `ADMIN`.

```json
Request:  {"grace_period_seconds": 300}
Response: 200 {"host_id", "new_agent_token": "<shown once>", "old_token_expires_at": "..."}
```

- Generates a new agent credential for the host.
- Old credential remains valid for `grace_period_seconds` (default 300, max 3600), then invalidated.
- Audit event: `CREDENTIAL_ROTATED`.

### 4.3 DELETE `/api/v1/hosts/{host_id}` (Safe Unregister)

**Auth:** operator `ADMIN`. Idempotent.

```json
Request:  {}   (no body)
Response: 200 {"id", "hostname", "enrollment_status": "REVOKED", "revoked_at": "..."}
```

- Sets `is_revoked=True`, `revoked_at=now`.
- Host record is retained as a tombstone (telemetry and audit history preserved; no cascade delete).
- The agent receives 401 on its next poll/heartbeat and stops.
- Docker containers are NOT deleted; removing them is a separate manual operation.

### 4.4 POST `/api/v1/hosts/{host_id}/re-enroll`

**Auth:** operator `ADMIN` — not the agent. Used after revocation to restore a host.

```json
Request:  {"new_bootstrap_token": true}
Response: 201 {"bootstrap_token": "<shown once>", "expires_at": "..."}
```

- Issues a fresh bootstrap token scoped to the existing hostname.
- The existing host row is reused; a new agent credential is issued to whoever completes enrollment with that bootstrap token.
- Re-enrollment does NOT implicitly un-revoke. Revocation is cleared only when the bootstrap token is consumed by the agent.

---

## 5. Modified Agent Endpoints

### 5.1 POST `/api/v1/agents/enroll` (modified)

```json
Request:  {
  "hostname": "david-lab",
  "bootstrap_token": "<single-use token>",
  "agent_version": "0.1.0", "platform": "Linux", ...
}
Response: 200 {"host_id": "...", "agent_token": "<shown once>"}
```

Changes from Phase 1-2:
- Field `enrollment_token` replaced by `bootstrap_token` (old field name accepted for backward compat during migration; maps to same validation path).
- Requires a valid, unconsumed, unexpired bootstrap token scoped to the presented hostname.
- Atomically marks the token consumed. If already consumed → `409 BOOTSTRAP_TOKEN_CONSUMED`.
- On success, issues a long-lived agent credential (as today).
- If the hostname matches an existing REVOKED host, the host is un-revoked and re-bound to the new credential.

### 5.2 POST `/api/v1/agents/heartbeat` (modified)

Response adds `docker_enabled`:

```json
Response: 200 {"host_id", "status", "server_time", "heartbeat_interval_seconds", "docker_enabled": true}
```

Agent refuses to execute Docker operations when `docker_enabled=false`.

### 5.3 POST `/api/v1/agents/commands/poll` (unchanged auth, extended response)

- Rejects `X-Host-Id` values matching `sim-*` prefix with `400 SIMULATED_HOST_REJECTED`.
- When the host's `docker_enabled=false`, poll returns an empty command list for `DEPLOY`-type ops (they remain QUEUED until Docker is enabled).

### 5.4 POST `/api/v1/agents/commands/{id}/result` (unchanged)

- Same auth, same semantics (first-write-wins, idempotent).
- Rejects `sim-` prefixed `X-Host-Id`.

---

## 6. Modified Application Endpoints (operator-authenticated)

All three mutation endpoints now require an operator session:

| Endpoint | Method | Auth | Notes |
|---|---|---|---|
| `/api/v1/applications/deploy` | POST | Operator Bearer or session | `403 DOCKER_NOT_AUTHORIZED` if host `docker_enabled=false` |
| `/api/v1/applications/{id}/start` | POST | Operator | Same check |
| `/api/v1/applications/{id}/stop` | POST | Operator | Same check |

Read endpoints (`GET /templates`, `/applications`, `/applications/{id}/container-state`, `/operations/{id}`, `/hosts*`, `/health`) remain unauthenticated (trusted-local model, Phase 3B scope).

---

## 7. Data Contract Changes (API responses)

### 7.1 `HostOut` (public `GET /hosts`, `/hosts/{id}`)

Adds fields:

```json
{
  ...existing...,
  "enrollment_status": "PENDING|ENROLLED|ONLINE|STALE|OFFLINE|REVOKED",
  "docker_enabled": false
}
```

`is_revoked` is retained for backward compatibility; `enrollment_status == "REVOKED"` is the canonical representation going forward.

### 7.2 `HeartbeatResponse` (agent)

Adds `docker_enabled: bool`.

---

## 8. Request/Response Examples

### Enrollment (happy path)

```http
POST /api/v1/agents/enroll
Content-Type: application/json

{
  "hostname": "david-lab",
  "bootstrap_token": "B7f9K2...",
  "agent_version": "0.2.0",
  "platform": "Linux",
  "platform_release": "6.12.113+deb13-amd64",
  "cpu_cores": 4,
  "total_memory_bytes": 8160437862
}
```

```http
HTTP/1.1 200 OK
{"host_id": "5ca406e8-...", "agent_token": "nm_9xK..."}
```

### Re-enrollment after revocation

```http
POST /api/v1/hosts/5ca406e8-.../re-enroll
Authorization: Bearer <operator-session>
{"new_bootstrap_token": true}
```

```http
HTTP/1.1 201 Created
{"bootstrap_token": "B7f9K2...", "expires_at": "2026-11-10T14:30:00Z"}
```

### Safe Unregister

```http
DELETE /api/v1/hosts/5ca406e8-...
Authorization: Bearer <operator-session>
```

```http
HTTP/1.1 200 OK
{"id": "5ca406e8-...", "hostname": "david-lab", "enrollment_status": "REVOKED", "revoked_at": "..."}
```

---

## 9. OpenAPI Alignment

The Phase 3B contract is additive to `docs/API.md` (Phase 1–2). A formal OpenAPI 3.1 spec is out of scope for Phase 3B (no OpenAPI file exists in the repo today; FastAPI generates `/api/openapi.json` at runtime). The contract above is the authoritative pre-implementation reference; FastAPI models/schemas in `backend/app/schemas/__init__.py` must be updated in lock-step when implemented.
