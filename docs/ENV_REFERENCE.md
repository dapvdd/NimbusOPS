# NimbusOps Environment Variable Reference

All variables use the `NIMBUSOPS_` prefix. Backend defaults live in
`backend/app/core/config.py`; the agent reads its own set (below). No secret
has a code default: an absent enrollment token disables enrollment.

## Backend (control server)

| Variable | Default | Purpose |
| --- | --- | --- |
| `NIMBUSOPS_DATABASE_URL` | `sqlite:///./nimbusops.db` | SQLite location (relative paths resolve against `backend/`). |
| `NIMBUSOPS_ENROLLMENT_TOKEN` | *(empty)* | Legacy shared enrollment secret. Empty ⇒ legacy enrollment disabled (503). Prefer bootstrap tokens. |
| `NIMBUSOPS_TOKEN_PEPPER` | *(empty)* | Extra pepper for agent-token hashes. If unset the enrollment token is the pepper. Set a random 32+ char value in production. |
| `NIMBUSOPS_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated exact origins. `*` is rejected at startup. |
| `NIMBUSOPS_STALE_THRESHOLD_SECONDS` | `90` | Heartbeat age before a host shows STALE. |
| `NIMBUSOPS_OFFLINE_THRESHOLD_SECONDS` | `600` | Heartbeat age before a host shows OFFLINE. |
| `NIMBUSOPS_TELEMETRY_RETENTION_ROWS` | `1440` | Bounded telemetry rows per host (oldest pruned). |
| `NIMBUSOPS_OPERATOR_SESSION_TTL_SECONDS` | `43200` | Operator session lifetime (12 h). |
| `NIMBUSOPS_CREDENTIAL_ROTATION_GRACE_SECONDS` | `300` | Dual-accept window after agent credential rotation. |
| `NIMBUSOPS_OP_CLAIM_TIMEOUT_SECONDS` | `600` | RUNNING op older than this is re-queued by the reconciler. |
| `NIMBUSOPS_BOOTSTRAP_TOKEN_TTL_SECONDS` | `600` | Default single-use bootstrap token TTL (max 3600). |
| `NIMBUSOPS_LOGIN_RATE_LIMIT_ATTEMPTS` | `5` | Failed logins per window before 429. |
| `NIMBUSOPS_LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `300` | Sliding window length. |

## Agent

| Variable | Default | Purpose |
| --- | --- | --- |
| `NIMBUSOPS_SERVER_URL` | `http://127.0.0.1:8000` | Control server base URL (http/https only). |
| `NIMBUSOPS_ENROLLMENT_TOKEN` | required | Bootstrap/enrollment secret presented once; identity persists to the state file. |
| `NIMBUSOPS_INTERVAL` | `30` | Cycle interval in seconds (clamped 5–3600). |
| `NIMBUSOPS_STATE_FILE` | `~/.nimbusops/agent.json` | Identity path (mode 0600). Contains the agent token — protect it. |

## Security notes

- Never commit `.env` (git-ignored). Rotate `NIMBUSOPS_TOKEN_PEPPER` only with a
  credential re-enrollment plan: changing it invalidates stored hashes.
- The frontend keeps the operator session token in memory only (never
  localStorage/cookies) by design; there is no server-side cookie session.
