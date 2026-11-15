# NimbusOps Deployment Runbook

Status: v1 release candidate · 2026-11-12 · Branch evidence: `feat/autonomous-phase4-6`

This runbook contains only commands verified in this program (local staging runs
and the automated suites). Anything not verified is marked as such.

## 1. Prerequisites

- Python 3.13 with a virtualenv at the repo root (`.venv/`).
- Node.js (LTS) for the frontend build.
- SQLite (bundled with Python). No external database service required.

## 2. Backend

```powershell
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt

# Required environment (never commit real values):
$env:NIMBUSOPS_ENROLLMENT_TOKEN = "<legacy shared token; empty disables legacy enrollment>"
$env:NIMBUSOPS_TOKEN_PEPPER     = "<random 32+ chars; mixes into stored token hashes>"
$env:NIMBUSOPS_DATABASE_URL     = "sqlite:///./nimbusops.db"   # or absolute path
$env:NIMBUSOPS_CORS_ORIGINS     = "http://localhost:5173"

# Run (bind loopback unless a reverse proxy fronts it):
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- On boot the app runs `create_all()` + `upgrade_phase3b()` (additive, idempotent)
  and seeds the approved template catalog (`nginx-demo`).
- Health/readiness: `GET /api/v1/health` → `{"status":"ok","database":"ok",...}`.
- The claim-timeout reconciler starts with the app (interval derived from
  `NIMBUSOPS_OP_CLAIM_TIMEOUT_SECONDS`).

## 3. Frontend

```powershell
cd frontend
npm ci
npm run build          # tsc -b && vite build -> dist/
npm run preview        # serve the production build locally
```

The SPA talks to `/api/v1` on its own origin; put a reverse proxy in front for
deployment (the dev server proxies are for development only).

## 4. Agent (on each managed host)

```bash
# Linux host example (install the agent from this repository)
python3 -m pip install psutil httpx
python3 -m pip install ./agent        # provides the `nimbusops-agent` CLI

# Bootstrap enrollment: an operator issues a single-use token in the UI
# (Hosts view -> issue bootstrap token). The token is a secret: pass it via a
# file or the environment, never on the command line.
printf '%s' '<bootstrap token>' > ~/.nimbusops/bootstrap.token
chmod 600 ~/.nimbusops/bootstrap.token
NIMBUSOPS_AGENT_SERVER_URL=http://<control-plane-host>:8000 \
python3 -m nimbusops_agent --bootstrap-token-file ~/.nimbusops/bootstrap.token
```

- Environment names are `NIMBUSOPS_AGENT_SERVER_URL`,
  `NIMBUSOPS_AGENT_BOOTSTRAP_TOKEN` (or `--bootstrap-token-file`),
  `NIMBUSOPS_AGENT_INTERVAL`, and `NIMBUSOPS_AGENT_STATE_FILE`. The legacy
  shared secret is `NIMBUSOPS_AGENT_ENROLLMENT_TOKEN` and is only for
  `NIMBUSOPS_ENROLLMENT_MODE=legacy` on the server.
- The entrypoint is `python -m nimbusops_agent` or the `nimbusops-agent`
  console script; both run `nimbusops_agent.main:main`.
- Identity is persisted to `~/.nimbusops/agent.json` (atomic replace, mode 0600
  on POSIX) on first enroll; subsequent runs reuse it with no secret.
  `NIMBUSOPS_AGENT_INTERVAL` is seconds (5–3600).
- The agent heartbeats, sends telemetry, polls for allowlisted operations
  (DEPLOY/START/STOP/RESTART/INVENTORY), and reports results. It refuses every
  Docker operation when the server says `docker_enabled=false`, and requires
  matching `nimbusops.managed`/`nimbusops.deployment` labels before mutating a
  container.

## 5. First operator

The control server has no default operator. Create one directly in the DB
(verified pattern, isolated staging DB):

```python
from app.core.db import session_scope
from app.core.security import hash_operator_password
from app.models import Operator
with session_scope() as db:
    db.add(Operator(username="admin", password_hash=hash_operator_password("<pw>"), role="ADMIN"))
```

Then log in via the UI. Login rate limit: 5 failed attempts / 300 s per username
(429 `RATE_LIMITED`), configurable via `NIMBUSOPS_LOGIN_RATE_LIMIT_*`.

## 6. Enabling Docker on a host (operator action)

`PATCH /api/v1/hosts/{id}` with an ADMIN session toggles `docker_enabled`.
Default is OFF for every new host; the server rejects Docker operations with
403 `DOCKER_NOT_AUTHORIZED` until enabled, and the agent double-checks.

## 7. Verification after install

1. `GET /api/v1/health` returns ok.
2. Agent appears under `/api/v1/hosts` with status ONLINE within one interval.
3. Telemetry metrics render on the host detail page.
4. Issue a bootstrap token in the UI; enroll a second host; verify isolation
   (operations on host A never touch host B — pinned by tests).

## 8. Not covered here (unverified in this program)

- Systemd unit installation, TLS termination, public-cloud VM provisioning:
  no production infrastructure was touched in this program; configure per your
  environment. The agent protocol is transport-agnostic (HTTP JSON).
