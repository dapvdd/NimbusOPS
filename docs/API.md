# NimbusOps API — Phase 1 (implemented)

All endpoints are mounted under `/api/v1`. Interactive docs: `/api/docs`
(OpenAPI: `/api/openapi.json`) when the server is running.

Deviations from the PRD section 17 planned endpoints are listed at the end.
Error responses use the contract in docs/SECURITY.md and DATA_CONTRACT.md;
all timestamps are UTC ISO-8601.

## Public (browser) endpoints — no auth in Phase 1

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
| 404 | `HOST_NOT_FOUND` | Unknown host id |
| 409 | — | (reserved; hostname conflicts currently rotate instead) |
| 422 | FastAPI `detail` shape | Malformed/out-of-range payload |
| 503 | `ENROLLMENT_DISABLED` | Server started without an enrollment token |

## Deviations from PRD section 17 planned endpoints

- Added `POST /api/v1/agents/enroll` (PRD's "agent credentials" entity
  requires a bootstrap path; not in the planned list).
- Heartbeat request may carry agent metadata (version/platform) so the
  dashboard's host panel reflects reality without a separate endpoint.
- `/hosts/{id}/containers`, `/templates`, `/deployments`, `/operations`,
  `/containers/{id}/start|stop`, `/agents/operations/{id}/result` are Phase 2
  scope and intentionally absent here.
