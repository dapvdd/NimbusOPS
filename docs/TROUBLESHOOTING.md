# NimbusOps Troubleshooting Guide

Symptoms verified against the code and test suites in this program.

## Control server

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `RuntimeError: NIMBUSOPS_CORS_ORIGINS must not contain '*'` | Wildcard origin | List exact origins, restart. |
| `503 ENROLLMENT_DISABLED` on enroll | Legacy token empty/unset | Issue a bootstrap token (preferred) or set the legacy token. |
| Login returns 429 `RATE_LIMITED` | ≥5 failed logins in 300 s for that username | Wait for the window or adjust `NIMBUSOPS_LOGIN_RATE_LIMIT_*`; correct passwords are also rejected while limited (fail closed). |
| 401 `OPERATOR_AUTH_REQUIRED` on mutation | Missing/expired/revoked session, or Authorization without `Bearer ` prefix | Re-login; the raw token alone is rejected (Phase 3B hardening). |
| 409 on bootstrap enroll | Token already consumed, or hostname taken by a live host | Issue a new token; revoked hostnames need operator bootstrap re-enroll. |
| `database: degraded` in /health | DB file unreachable | Check `NIMBUSOPS_DATABASE_URL` path/permissions. |

## Hosts / agents

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Host shows STALE/OFFLINE | No heartbeat within threshold (90 s / 600 s defaults) | Check agent process and network; agent retries with exponential backoff; no operator action needed once connectivity returns (natural reconnect verified). |
| `401` on agent endpoints after restart | Credential rotated or host revoked | Re-enroll via bootstrap token, or rotate within the grace window. |
| Agent logs `credentials rejected, stopping` (exit 3) | Server revoked host / rotated token | Operator re-enroll required. |
| 403 `DOCKER_NOT_AUTHORIZED` | Host `docker_enabled=false` | ADMIN enables Docker for that host; server AND agent both enforce. |
| 403 `UNAPPROVED_OPERATION` (agent) | Container name lacks `nimbusops-` prefix, or op not in allowlist | Only managed containers and DEPLOY/START/STOP/RESTART/INVENTORY are permitted. |
| Operation stuck RUNNING | Agent died mid-run | The reconciler re-queues ops past `NIMBUSOPS_OP_CLAIM_TIMEOUT_SECONDS` (≤ next reconcile pass, ≤ interval+30 s). |
| Operation result UNKNOWN | Agent could not verify (e.g., pull timeout) | Honest outcome by design; check `error_message` in the activity view, retry after fixing. |
| `database is locked` under load | Non-WAL deployment | Phase 6 enables WAL on connect; verify with `PRAGMA journal_mode` ⇒ `wal`. Old pre-Phase-6 DBs converge on next boot. |

## Frontend

| Symptom | Likely cause | Action |
| --- | --- | --- |
| "Real infrastructure unavailable" on Servers | API fetch failed | Check control server + CORS origins; use Retry. |
| Operator logged out after refresh | Session is memory-only by design (token never persisted in the browser) | Re-login. |
| Activity list empty | No operations yet, or filter active | Clear status filter; deploy something. |

## Diagnostics that never leak secrets

- Server logs contain host ids, op ids, usernames, error codes — never tokens
  or passwords (pins in suite).
- `GET /api/v1/operations/{id}/events` shows the append-only audit trail for
  any operation (CREATED → CLAIMED → RESULT/TIMED_OUT).
