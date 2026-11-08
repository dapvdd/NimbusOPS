# NimbusOps Local Development Guide (Phases 1–2)

Complete setup for the single-host monitoring stack (Phase 1) and the
Docker deployment MVP (Phase 2): FastAPI control server, React dashboard,
and the NimbusOps host agent.

## Prerequisites

- Python 3.11+ (3.13 used during development)
- Node.js 20+ (24 used during development)
- Docker Engine (Phase 2 deployment features only) — OPTIONAL. Monitoring
  works without it; deployment operations report `DOCKER_UNAVAILABLE`.
  On the development machine Docker was NOT available; see
  docs/PHASE2_VERIFICATION.md.
- No global installs: everything lives in a repo-local virtualenv and
  `frontend/node_modules`.

## 1. Backend (control server)

```bash
# From the repository root
python -m venv .venv
# Windows: .venv\Scripts\python -m pip install -r backend/requirements.txt
# Linux/macOS:
.venv/bin/python -m pip install -r backend/requirements.txt

# Configure (placeholders are safe; the SQLite DB is created on startup)
cp backend/.env.example backend/.env
# Edit backend/.env: set NIMBUSOPS_ENROLLMENT_TOKEN to a long random value
```

Start the API (from `backend/`):

```bash
# Windows: ..\.venv\Scripts\python -m uvicorn app.main:app --port 8000
..\.venv\bin\python -m uvicorn app.main:app --port 8000
```

Verify: <http://127.0.0.1:8000/api/v1/health> → `{"status":"ok",...}`.
Interactive API docs: <http://127.0.0.1:8000/api/docs>.

The SQLite database (`backend/nimbusops.db`) is created automatically on
first start. Delete the file to reset all state.

## 2. Frontend (dashboard)

```bash
cd frontend
npm install
npm run dev       # http://localhost:5173, proxies /api to 127.0.0.1:8000
```

Production build: `npm run build` (output in `frontend/dist/`).

## 3. Agent (runs on the managed Linux host)

On the Ubuntu VM (or locally for a smoke test on another OS):

```bash
python3 -m venv .venv
.venv/bin/pip install -r agent/requirements.txt

# Point at the control server; token must match the server's
# NIMBUSOPS_ENROLLMENT_TOKEN for the first enrollment.
export NIMBUSOPS_AGENT_SERVER_URL=http://<server-ip>:8000
export NIMBUSOPS_AGENT_ENROLLMENT_TOKEN=<same-as-server>
export NIMBUSOPS_AGENT_INTERVAL=30

cd agent
../.venv/bin/python -m nimbusops_agent.main
```

First run enrolls the agent and stores its identity (host_id + agent
token) in `~/.nimbusops/agent.json` (mode 0600 on Linux). Later runs
reuse that identity; the enrollment token is not needed again.

Loopback `http://127.0.0.1` is acceptable only for local development.
Across machines/networks the server must be behind HTTPS or a secure
private tunnel — the agent does not negotiate TLS itself.

`--once` runs a single heartbeat+telemetry cycle and exits (useful for
smoke tests). `Ctrl+C` stops the agent gracefully.

### Docker deployment features (Phase 2)

When the managed host has a working Docker Engine, the agent picks up
approved operations (deploy/start/stop) each polling cycle — no extra
flags. Requirements on the managed host:

- `docker` CLI on the agent's PATH, daemon reachable (no root required
  beyond normal Docker group membership).
- Outbound HTTP to the control server only; no inbound ports; the Docker
  socket is never exposed over TCP by NimbusOps.
- The agent touches only containers named `nimbusops-*` and only the
  approved `nginx-demo` template (image `nginx:1.27-alpine`, published on
  host port 8080). Nothing else on the host's Docker is modified.

When Docker is absent/broken, deployment operations report
`DOCKER_UNAVAILABLE`/`DOCKER_FAILURE` and monitoring continues unaffected.

### systemd service (example only — review before any real install)

See `agent/nimbusops-agent.service.example`. It is a template: adjust
paths and user, and do not enable it on machines you do not control.

## 4. Running the tests

```bash
# Backend + agent + integration (from repo root)
.venv/Scripts/python -m pytest            # Windows
.venv/bin/python -m pytest                # Linux/macOS

# Frontend (from frontend/)
npm test

# Frontend production build (type-checks as a side effect)
npm run build
```

The integration suite starts a real uvicorn server on `127.0.0.1:8991`
(Phase 1) and `127.0.0.1:8992` (Phase 2) and drives them with the real
agent code. Phase 2 integration mocks only the Docker executor boundary
(no Docker Engine on the development machine — labeled MOCKED); everything
else is real HTTP/SQLite/protocol. It does NOT require an Ubuntu VM; the
Ubuntu + real-Docker verification is tracked separately in the docs.

## 5. Full local stack (all three components)

1. Terminal 1 — backend (see §1), port 8000.
2. Terminal 2 — frontend dev server (see §2), port 5173.
3. Terminal 3 — agent (see §3) with `NIMBUSOPS_AGENT_SERVER_URL=http://127.0.0.1:8000`.

Open <http://localhost:5173>: the Overview shows the enrolled host with
live CPU/RAM/disk telemetry updating every 30 seconds. The Applications
view deploys/starts/stops the approved Nginx demo (requires Docker on the
agent host; the deployed app answers on <http://localhost:8080>).

## 6. Configuration reference

Server (`backend/.env`, prefix `NIMBUSOPS_`): see `backend/.env.example`.
Agent (env or flags): see `agent/.env.example`.

## 7. Resetting state

- Stop the agent; delete `backend/nimbusops.db`; restart the backend.
- Agent re-enrollment: delete `~/.nimbusops/agent.json` on the host and
  restart the agent (rotates the agent token; the host keeps its UUID).
