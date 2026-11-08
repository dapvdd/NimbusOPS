# NimbusOps

A centralized, cloud-ready platform for monitoring Linux hosts and managing Docker application deployments across private and public infrastructure.

## Project status

**Phase 1 — Single-host monitoring: implemented and locally verified.**
The control server (FastAPI), dashboard (React/Vite/Tailwind), and host
agent (Python/psutil) are implemented and tested; see
[Phase 1 verification](docs/PHASE1_VERIFICATION.md) for what was executed
and what remains blocked (Ubuntu VM gate).

**Phase 2 — Docker deployment MVP: implemented; real-Docker verification
blocked on the development machine** (no Docker Desktop/WSL installed;
nothing was installed without authorization). The full deployment
pipeline — approved Nginx template, durable operation tracking, agent-side
constrained Docker execution, start/stop lifecycle, dashboard Applications
view — is implemented with mocked-Docker tests; see
[Phase 2 verification](docs/PHASE2_VERIFICATION.md). Docker interaction
uses only fixed argv invocations of the Docker CLI, scoped by
`nimbusops.*` labels to NimbusOps-created resources.

NimbusOps is an academic Cloud Computing project at Sekolah Vokasi,
Universitas Gadjah Mada. Development is **product-first, local-first, hybrid-ready**.
The supplied PRD v1.1 is dated 8 November 2026 and marked **DRAFT / REVIEW REQUIRED**;
group and lecturer approval has not been independently established.

## Problem and product

Checking Linux servers through separate SSH sessions and Docker commands makes
monitoring, repeatable deployments, and evidence collection difficult. NimbusOps
aims to bring host visibility and approved Docker application operations into one
web dashboard. It is not a cloud provider or a replacement for Docker Engine.

### Initial product: v0.1 (planned)

- Monitor real CPU, RAM, and disk metrics from one isolated Ubuntu VM.
- Show host connectivity, stale data, and managed Docker container status.
- Deploy an approved Nginx demo and verify its container state and HTTP response.
- Start and stop only the managed demo application.
- Show genuine operation IDs, results, and errors, including unknown outcomes.
- Require authentication for mutations and for demonstrations accessed by others.

Multi-host management, public cloud, advanced RBAC, and backup are later milestones.
Kubernetes, high availability, autoscaling, and automatic VM provisioning are not
part of the initial product.

## Proposed technology stack

The PRD specifies React/Vite for the dashboard, Python/FastAPI for the control
server, an Ubuntu host agent, and Docker Engine/Compose for approved applications.
SQLite is permitted for v0.1; PostgreSQL is a later option when concurrency and
multi-host needs justify it. Agent implementation language, dependency versions,
and transport details remain pending. No dependencies have been installed here.

## High-level architecture

```text
Dashboard -> Control Server -> Host Agent -> Docker Engine
                 ^                 |
                 +-- outbound -----+
                     agent connection
```

The first line represents logical responsibility, not an inbound agent connection.
The agent initiates authenticated communication with the control server and uses
the Docker socket locally. The browser never accesses the agent or Docker directly.
See [Architecture](docs/ARCHITECTURE.md) for boundaries and pending decisions,
[API](docs/API.md) for the implemented endpoint contract,
[Data contract](docs/DATA_CONTRACT.md) for units/thresholds, and
[Security](docs/SECURITY.md) for the Phase 1 trust model.

## Quick start (Phase 1)

Full setup: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). Short version:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt   # Windows
cp backend/.env.example backend/.env   # set NIMBUSOPS_ENROLLMENT_TOKEN
# terminal 1:  cd backend && ..\.venv\Scripts\python -m uvicorn app.main:app --port 8000
# terminal 2:  cd frontend && npm install && npm run dev   -> http://localhost:5173
# terminal 3:  agent (see docs/DEVELOPMENT.md §3) enrolls and starts reporting
```

## Development milestones

| Phase | Planned outcome | Product milestone |
| --- | --- | --- |
| 0 | Repository foundation | Preparation for PRD approval gate M0 |
| 1 | Single-host monitoring (implemented) | First portion of v0.1 |
| 2 | Docker inventory and approved Nginx lifecycle (implemented; live Docker verification blocked) | Complete v0.1 / M1 |
| 3 | Two-host management | v0.2 / M2 |
| 4 | Private-public infrastructure | v0.3 / M3 |
| 5 | Advanced reliability and security | Optional v1.0 / M4 |

Acceptance criteria are in the [Roadmap](docs/ROADMAP.md). Completion of repository
foundation does not imply approval of the PRD or completion of a product milestone.

## Repository guide

| Path | Purpose |
| --- | --- |
| [docs/PRD.md](docs/PRD.md) | Traceable digest of the supplied v1.1 source |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Planned components, boundaries, and decisions |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phase acceptance gates |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Local setup for server, dashboard, agent, tests |
| [docs/API.md](docs/API.md) | Implemented Phase 1–2 API contract |
| [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md) | Units, timestamps, thresholds, retention |
| [docs/SECURITY.md](docs/SECURITY.md) | Enrollment/auth model and known limits |
| [docs/PHASE1_VERIFICATION.md](docs/PHASE1_VERIFICATION.md) | Executed tests and live evidence (Phase 1) |
| [docs/PHASE2_VERIFICATION.md](docs/PHASE2_VERIFICATION.md) | Executed tests and evidence (Phase 2) |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Group contribution and validation workflow |
| `frontend/` | React dashboard (monitoring + applications) |
| `backend/` | FastAPI control server (monitoring + deployment control plane) |
| `agent/` | Python host agent (telemetry + constrained Docker execution) |
| `infra/` | Reserved for future development infrastructure definitions |

## Contributing

Read the PRD, architecture, and current phase acceptance criteria before making
changes. Use focused branches and conventional commits, preserve existing work,
and submit changes for group review. See [CONTRIBUTING.md](CONTRIBUTING.md).
Team ownership, schedule, budget, lecturer approval, and final cloud-demo policy
remain to be confirmed.
