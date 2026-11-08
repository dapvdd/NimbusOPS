# NimbusOps API — Phase 2 (Phases 1–2 implemented)

All endpoints are mounted under `/api/v1`. Interactive docs: `/api/docs`
(OpenAPI: `/api/openapi.json`) when the server is running.

Deviations from the PRD section 17 planned endpoints are listed at the end.
Error responses use the contract in docs/SECURITY.md and DATA_CONTRACT.md;
all timestamps are UTC ISO-8601.

## Public (browser) endpoints — no auth (trusted-local; see SECURITY.md)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health` | Liveness + DB check |
| GET | `/api/v1/hosts` | All hosts with status + latest metrics |
| GET | `/api/v1/hosts/{id}` | One host, same shape |
| GET | `/api/v1/hosts/{id}/metrics?limit=&before=` | Telemetry history, newest first, `limit` 1–1440 (default 120) |

`GET /hosts` response:

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
      "is_revoked": false
    }
  ],
  "count": 1
}
```

`latest_metrics` is `null` when the host never reported telemetry — never
zeros. Status semantics: docs/DATA_CONTRACT.md.

## Agent endpoints

| Method | Path | Auth |
| --- | --- | --- |
| POST | `/api/v1/agents/enroll` | Enrollment token in body |
| POST | `/api/v1/agents/heartbeat` | `X-Host-Id` + `Authorization: Bearer <agent-token>` |
| POST | `/api/v1/agents/telemetry` | same |

`POST /agents/enroll` body:

```json
{
  "hostname": "web-01",
  "enrollment_token": "<operator token>",
  "agent_version": "0.1.0", "platform": "Linux",
  "platform_release": "6.8.0-45-generic", "cpu_cores": 4,
  "total_memory_bytes": 8589934592, "boot_time": "2026-11-07T10:00:00Z"
}
```

→ `200 {"host_id": "...", "agent_token": "<shown exactly once>"}`

Only `hostname` and `enrollment_token` are required; metadata is optional.

`POST /agents/heartbeat` body: any subset of the metadata fields above
(except hostname). → `200 {"host_id","status","server_time",
"heartbeat_interval_seconds"}`.

`POST /agents/telemetry` body:

```json
{
  "recorded_at": "2026-11-08T12:00:00Z",
  "cpu_percent": 23.4,
  "memory_used_bytes": 3221225472,
  "memory_total_bytes": 8589934592,
  "disk_used_bytes": 21474836480,
  "disk_total_bytes": 107374182400
}
```

→ `200 {"host_id","recorded_at","retained":true,"status"}`. Percent fields
are re-derived server-side; `used > total` and out-of-range percentages are
rejected with 422.

## Error contract

Non-validation errors:

```json
{ "error": { "code": "UNAUTHORIZED", "message": "invalid agent credential" } }
```

| Status | Codes | When |
| --- | --- | --- |
| 401 | `UNAUTHORIZED` | Missing/invalid enrollment or agent token; revoked credential |
| 403 | `FORBIDDEN_HOST` | Agent posting a result for another host's operation |
| 404 | `HOST_NOT_FOUND`, `DEPLOYMENT_NOT_FOUND`, `OPERATION_NOT_FOUND` | Unknown id |
| 409 | — | (reserved; duplicate protection is idempotent-return, not 409) |
| 422 | FastAPI `detail` shape; `INVALID_TEMPLATE` via error contract | Malformed/out-of-range payload; unapproved template |
| 503 | `ENROLLMENT_DISABLED` | Server started without an enrollment token |

## Applications & deployments (Phase 2)

### Public (browser) endpoints — trusted-local

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/templates` | Approved deployment templates |
| GET | `/api/v1/applications` | Managed applications + last operation + container state |
| POST | `/api/v1/applications/deploy` | Create deployment + QUEUED operation → 202 |
| POST | `/api/v1/applications/{id}/start` | Queue START → 202 |
| POST | `/api/v1/applications/{id}/stop` | Queue STOP → 202 |
| GET | `/api/v1/applications/{id}/container-state` | Agent-reported container state (honest unknown) |
| GET | `/api/v1/operations/{id}` | Operation status/evidence/errors |

`POST /applications/deploy` body: `{"host_id": "...", "template_key": "nginx-demo"}`.

→ `202 {"operation_id","deployment_id","host_id","template_key","status":"QUEUED",
"container_name","app_url","deduplicated":false}`

Duplicate protection: deploying the same template on the same host while an
operation is QUEUED/RUNNING returns the **same** operation with
`deduplicated: true` — repeated clicks cannot create duplicate deployments.
After a terminal state, a new deploy creates a **new** operation on the same
deployment.

Operation states: `QUEUED → RUNNING → SUCCEEDED | FAILED | UNKNOWN`.
`SUCCEEDED` requires agent-reported verifiable evidence (`container_state`
from `docker ps` + optional `http_ok` probe stored in `result`). `UNKNOWN`
means the outcome could not be determined (timeout/unverifiable) — it is
never silently reported as success or failure.

`GET /applications` response (excerpt):

```json
{
  "applications": [
    {
      "deployment_id": "uuid",
      "host_id": "uuid",
      "hostname": "web-01",
      "template_key": "nginx-demo",
      "container_name": "nimbusops-nginx-demo-hxxxxxxxx",
      "app_url": "http://localhost:8080/",
      "last_operation": { "id": "...", "op_type": "DEPLOY", "status": "SUCCEEDED",
        "result": {"container_state": "RUNNING", "http_ok": true}, "...": "..." },
      "container_state": "RUNNING | EXITED | ... | null",
      "http_ok": true | false | null,
      "reported_at": "... | null"
    }
  ],
  "count": 1
}
```

`container_state` is `null`/`NOT_REPORTED` until the agent reports real
Docker state — never fabricated.

### Agent command endpoints

| Method | Path | Auth |
| --- | --- | --- |
| POST | `/api/v1/agents/commands/poll` | `X-Host-Id` + Bearer agent token |
| POST | `/api/v1/agents/commands/{op_id}/result` | same |

Poll **claims** atomically (QUEUED→RUNNING): each command is delivered to
exactly one poll; claimed commands are not re-delivered on reconnect (the
operation stays RUNNING — an honest "claimed, outcome pending" state).
Results are first-write-wins: a duplicate result submission gets
`accepted: false` and never overwrites recorded evidence.

Poll response: `{"commands": [ { ...operation, "template": {key, image,
container_port, host_port, container_name} } ]}`.

Result body: `{"status": "SUCCEEDED|FAILED|UNKNOWN", "result": {...},
"error_code": "...", "error_message": "..."}` →
`200 {"operation_id","status","accepted": true|false}`.

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
