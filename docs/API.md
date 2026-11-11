# NimbusOps API — Phases 1–3B implemented

All endpoints are mounted under `/api/v1`. Interactive docs: `/api/docs`
(OpenAPI: `/api/openapi.json`) when the server is running.

Deviations from the PRD section 17 planned endpoints are listed at the end.
Error responses use the contract in docs/SECURITY.md and DATA_CONTRACT.md;
all timestamps are UTC ISO-8601. Typed errors serialize as
`{"error": {"code", "message"}}`.

## Public (browser) endpoints — no auth (trusted-local reads; see SECURITY.md)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health` | Liveness + DB check |
| GET | `/api/v1/hosts` | All hosts with status + latest metrics |
| GET | `/api/v1/hosts/{id}` | One host, same shape |
| GET | `/api/v1/hosts/{id}/metrics?limit=&before=` | Telemetry history, newest first, `limit` 1–1440 (default 120) |

`GET /hosts` response (Phase 3B adds `enrollment_status` and
`docker_enabled`; §7.1 of the Phase 3B contract):

```json
{
  "hosts": [
    {
      "id": "uuid",
      "hostname": "web-01",
      "status": "ONLINE | STALE | OFFLINE",
      "agent_version": "0.1.0",
      "platform": "Linux",
      "platform_release": "6.8.0-45-generic",
      "cpu_cores": 4,
      "total_memory_bytes": 8589934592,
      "boot_time": "2026-11-07T10:00:00Z",
      "enrolled_at": "...",
      "last_seen_at": "... | null",
      "last_telemetry_at": "... | null",
      "latest_metrics": { "recorded_at": "...", "cpu_percent": 23.4,
        "memory_used_bytes": 1, "memory_total_bytes": 2,
        "memory_used_percent": 37.5, "disk_used_bytes": 1,
        "disk_total_bytes": 2, "disk_used_percent": 20.0 },
      "is_revoked": false,
      "enrollment_status": "PENDING | ENROLLED | ONLINE | STALE | OFFLINE | REVOKED",
      "docker_enabled": false
    }
  ],
  "count": 1
}
```

`is_revoked` is retained for backward compatibility;
`enrollment_status == "REVOKED"` is canonical going forward.

## Operator authentication (Phase 3B — decision O1)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/operators/login` | — | `{"username","password"}` → `200 {"session_token","operator_id","role","expires_at"}` |
| POST | `/api/v1/operators/logout` | Bearer session | Invalidates the session; idempotent (`200` even if already gone) |
| GET | `/api/v1/operators/me` | Bearer session | `{"operator_id","username","role"}` |

- Sessions are 256-bit random tokens, shown once to the client, stored only
  as keyed SHA-256 hashes; TTL 12 h (`NIMBUSOPS_OPERATOR_SESSION_TTL_SECONDS`).
- Errors: missing/invalid/expired/revoked session →
  `401 OPERATOR_AUTH_REQUIRED`; role mismatch → `403 OPERATOR_FORBIDDEN`.
- Roles: `ADMIN` (full control) and `VIEWER` (read-only operator endpoints).
- The first operator is created out-of-band by script (never via API):
  `backend/.venv/Scripts/python -m backend.scripts.create_operator --username admin`
  (prompts for a password, ≥12 chars, PBKDF2-SHA256 240k iterations).

## Bootstrap token management (Phase 3B — operator `ADMIN`)

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/operators/bootstrap-tokens` | `{"hostname","expires_in_seconds"?}` (default 600, max 3600) → `201 {"id","hostname","token","expires_at","created_at"}` |
| GET | `/api/v1/operators/bootstrap-tokens` | List (no token material): `id, hostname, created_at, expires_at, consumed_at, consumed_by_host_id, revoked_at` |
| DELETE | `/api/v1/operators/bootstrap-tokens/{id}` | Revoke an unconsumed token; idempotent; consumed → `409 BOOTSTRAP_TOKEN_CONSUMED` |

`token` is returned exactly once and never stored in plaintext server-side.
Audit events `BOOTSTRAP_ISSUED` / `BOOTSTRAP_REVOKED` are appended to
`host_events` (append-only).

## Host lifecycle (Phase 3B — operator `ADMIN`)

| Method | Path | Purpose |
| --- | --- | --- |
| PATCH | `/api/v1/hosts/{id}` | `{"docker_enabled": bool}` — the only operator-settable field here → `200` host |
| POST | `/api/v1/hosts/{id}/rotate-credential` | `{"grace_period_seconds"?}` (default 300, max 3600) → `200 {"host_id","new_agent_token","old_token_expires_at"}` |
| DELETE | `/api/v1/hosts/{id}` | Revoke-to-tombstone: `is_revoked=true`, `enrollment_status="REVOKED"`; idempotent; row and telemetry retained, never deleted |
| POST | `/api/v1/hosts/{id}/re-enroll` | `{"new_bootstrap_token": true}` → `201 {"bootstrap_token","expires_at","hostname"}` |

- Rotation: new credential works immediately; the old one stays valid for
  the grace window (dual-hash check), then → `401`. Audit:
  `CREDENTIAL_ROTATED`.
- Revocation: the agent receives `401 HOST_REVOKED` on its next call;
  containers are NOT deleted. Audit: `HOST_REVOKED`.
- Re-enroll does NOT un-revoke by itself: the host is restored to
  `ENROLLED` only when an agent consumes the issued bootstrap token
  (same-host re-bind; identity UUID preserved). Audit:
  `RE_ENROLL_REQUESTED`, then `RE_ENROLLED`.

## Agent endpoints

### Enrollment — `POST /api/v1/agents/enroll` (Phase 3B §5.1)

```json
Request:  {"hostname": "david-lab", "bootstrap_token": "<single-use>"}
          // transition (O5): {"hostname": "...", "enrollment_token": "<legacy shared token>"}
Response: 200 {"host_id": "...", "agent_token": "<shown once>"}
```

- Preferred: a valid, unconsumed, unexpired **bootstrap token scoped to the
  presented hostname**. Atomically marked consumed.
  Errors: unknown/revoked/wrong-hostname → `401 BOOTSTRAP_TOKEN_INVALID`;
  expired → `410 BOOTSTRAP_TOKEN_EXPIRED`; replay → `409 BOOTSTRAP_TOKEN_CONSUMED`.
- Legacy shared token still works during the Phase 3B transition (removed in
  Phase 4). The old *silent un-revoke* is removed: a REVOKED hostname cannot
  be re-taken via the legacy token (`409 HOSTNAME_TAKEN`); use the operator
  re-enroll flow above.
- Simulated hostnames (`sim-*`) are rejected server-side:
  `400 SIMULATED_HOST_REJECTED`.

### Heartbeat — `POST /api/v1/agents/heartbeat` (Phase 3B §5.2)

Response adds `docker_enabled`:

```json
{"host_id": "...", "status": "ONLINE", "server_time": "...",
 "heartbeat_interval_seconds": 30, "docker_enabled": false}
```

The agent refuses Docker operations when `docker_enabled=false`.

### Telemetry — `POST /api/v1/agents/telemetry`

Unchanged from Phase 1 (credential-gated, validated, retained).

### Agent command endpoints (Phase 3B §5.3/§5.4)

| Method | Path | Auth |
| --- | --- | --- |
| POST | `/api/v1/agents/commands/poll` | `X-Host-Id` + Bearer agent token |
| POST | `/api/v1/agents/commands/{op_id}/result` | same |

- `X-Host-Id` values with the `sim-` prefix → `400 SIMULATED_HOST_REJECTED`
  (server-side guard, mirroring the browser-side guard).
- Poll **claims** atomically (QUEUED→RUNNING) and stamps a claim deadline;
  when the host's `docker_enabled=false`, DEPLOY ops are **not claimed**
  (they stay QUEUED until an operator enables Docker).
- Claim-timeout reconciliation (Phase 3B): a RUNNING op past its deadline is
  re-queued automatically (background sweep + lazy pre-poll check) and is
  re-delivered on the next poll; terminal ops are never touched.
- Results are first-write-wins: duplicate submissions get `accepted: false`.

## Applications & deployments (Phase 2; Phase 3B auth changes)

### Read endpoints — no auth (trusted-local)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/templates` | Approved deployment templates |
| GET | `/api/v1/applications` | Managed applications + last operation + container state |
| GET | `/api/v1/applications/{id}/container-state` | Agent-reported container state (honest unknown) |
| GET | `/api/v1/operations/{id}` | Operation status/evidence/errors |

### Mutation endpoints — operator `ADMIN` required (Phase 3B AC-01)

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| POST | `/api/v1/applications/deploy` | Operator Bearer (ADMIN) | `403 DOCKER_NOT_AUTHORIZED` when host `docker_enabled=false` |
| POST | `/api/v1/applications/{id}/start` | Operator Bearer (ADMIN) | Same check |
| POST | `/api/v1/applications/{id}/stop` | Operator Bearer (ADMIN) | Same check |

→ `202 {"operation_id","deployment_id","host_id","template_key","status":"QUEUED",
"container_name","app_url","deduplicated":false}`

Without a session → `401 OPERATOR_AUTH_REQUIRED`; with a VIEWER session →
`403 OPERATOR_FORBIDDEN`.

Duplicate protection is unchanged: an in-flight operation is returned with
`deduplicated: true`; a new operation is created only after a terminal state.

Operation states: `QUEUED → RUNNING → SUCCEEDED | FAILED | UNKNOWN`.
`SUCCEEDED` requires agent-reported verifiable evidence. `UNKNOWN` means the
outcome could not be determined — it is never silently reported as success or
failure.

## Error codes (Phase 3B additions)

| Status | Code | When |
| --- | --- | --- |
| 400 | `SIMULATED_HOST_REJECTED` | `sim-*` hostname/X-Host-Id at any agent endpoint |
| 401 | `OPERATOR_AUTH_REQUIRED` | Missing/invalid/expired operator session |
| 401 | `BOOTSTRAP_TOKEN_INVALID` | Unknown, revoked, or wrong-hostname bootstrap token |
| 401 | `HOST_REVOKED` | Agent call with a revoked credential |
| 403 | `OPERATOR_FORBIDDEN` | Role check failed (VIEWER on ADMIN endpoint) |
| 403 | `DOCKER_NOT_AUTHORIZED` | Docker op on a host with `docker_enabled=false` |
| 409 | `BOOTSTRAP_TOKEN_CONSUMED` | Token replay, or revoke of a consumed token |
| 410 | `BOOTSTRAP_TOKEN_EXPIRED` | Expired bootstrap token |

Existing codes (`UNAUTHORIZED`, `FORBIDDEN_HOST`, `HOST_NOT_FOUND`,
`HOSTNAME_TAKEN`, `ENROLLMENT_DISABLED`, `DEPLOYMENT_NOT_FOUND`,
`OPERATION_NOT_FOUND`, `INVALID_TEMPLATE`, `INVALID_OPERATION`,
`DOCKER_UNAVAILABLE`, `DOCKER_FAILURE`, `TIMEOUT`, `AGENT_UNREACHABLE`,
`INTERNAL`) are unchanged.

## Deviations from PRD section 17 planned endpoints

- Added `POST /api/v1/agents/enroll` (PRD's "agent credentials" entity
  requires a bootstrap path; not in the planned list).
- Heartbeat request may carry agent metadata (version/platform) so the
  dashboard's host panel reflects reality without a separate endpoint.
- Phase 2 endpoint names: `/templates`, `/applications/*`,
  `/operations/{id}`, `/agents/commands/*` replace the PRD's planned
  `/deployments`, `/containers/{id}/start|stop`,
  `/agents/operations/{id}/result` shapes — deployment identity is the
  managed application (one per host+template), and container state is
  agent-reported rather than a separate container entity.
- Phase 3B adds the operator namespace (`/operators/*`), host lifecycle
  actions on `/hosts/{id}`, and `host_events` audit — mirroring the PRD's
  RBAC intent (Phase 5) earlier, scoped to ADMIN/VIEWER.
