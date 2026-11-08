# NimbusOps

A centralized, cloud-ready platform for monitoring Linux hosts and managing Docker application deployments across private and public infrastructure.

## Project status

**Phase 0 — Repository Foundation.** This repository contains documentation and
reserved component directories only. Monitoring, APIs, authentication, deployment,
and the dashboard are planned; none is implemented or verified as operational.
There are no installation or run commands yet.

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
See [Architecture](docs/ARCHITECTURE.md) for boundaries and pending decisions.

## Development milestones

| Phase | Planned outcome | Product milestone |
| --- | --- | --- |
| 0 | Repository foundation | Preparation for PRD approval gate M0 |
| 1 | Single-host monitoring | First portion of v0.1 |
| 2 | Docker inventory and approved Nginx lifecycle | Complete v0.1 / M1 |
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
| [CONTRIBUTING.md](CONTRIBUTING.md) | Group contribution and validation workflow |
| `frontend/` | Reserved for the dashboard |
| `backend/` | Reserved for the control server |
| `agent/` | Reserved for the host agent |
| `infra/` | Reserved for future development infrastructure definitions |

The four component directories contain only `.gitkeep`. An `.env.example` is
intentionally deferred until real configuration variables are defined; Phase 0
has no runtime configuration contract.

## Contributing

Read the PRD, architecture, and current phase acceptance criteria before making
changes. Use focused branches and conventional commits, preserve existing work,
and submit changes for group review. See [CONTRIBUTING.md](CONTRIBUTING.md).
Team ownership, schedule, budget, lecturer approval, and final cloud-demo policy
remain to be confirmed.
