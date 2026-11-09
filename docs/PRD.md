# NimbusOps — PRD v1.1 Source Digest

> Dokumen konsolidasi terbaru: [Final Consolidated PRD v2.0](PRD-v2.0.md)
> (9 November 2026, **FINAL DRAFT — menunggu persetujuan tim/dosen**).
> Digest v1.1 ini dipertahankan sebagai riwayat sumber.

## Provenance and status

This is a structured **digest**, not a verbatim replacement or a newly approved
PRD. Primary source: `NimbusOps_PRD_v1.1_Product_First_Hybrid_Ready.docx`, supplied
in the user's Downloads folder and read for Phase 0. Obtain the original from the
document owner for full wording and tables; the binary is not committed here.
If this digest differs from the source, consult the DOCX and resolve with the group.

- Version/date: v1.1, 8 November 2026.
- Source status: **DRAFT / REVIEW REQUIRED**, for group/lecturer discussion, not
  proof of implementation. Approval has not been independently established.
- Institution: Sekolah Vokasi Universitas Gadjah Mada, Cloud Computing course.
- Owner: NimbusOps group; member names and responsibilities await confirmation.
- Source SHA-256: `ADFC8F8D192EEF1D4CEC7CF97A736308F6B5B7DBABCF068644D8E2CD6EA51594`.
- Source baseline: `PRD_NimbusOps.docx` v1.0.0, 24 sections and seven modules.

## Lecturer summary and requested decisions

NimbusOps monitors Linux hosts and deploys approved Docker applications through
a web dashboard. Start with one real Ubuntu VM and Nginx; target at least one
private and one public-cloud host using the same agent protocol later. Public
cloud depends on provider access and lecturer approval, not initial development.

The source requests agreement on product/demo outcomes, whether real public cloud
is mandatory or an isolated fallback is acceptable, progressive versions,
evaluation criteria, budget, schedule, and evidence. Kubernetes, autoscaling,
automatic VM provisioning, HA, and a specific cloud provider are not promised.

## Sections 1–5: Context, problem, product, objectives

The source adapts the original PRD to product-first, local-first development.
Fragmented SSH and Docker CLI workflows complicate monitoring, repeated deployment,
and cross-network management. NimbusOps coordinates a dashboard, control server,
and host agent; it is neither a cloud provider nor a Docker replacement.

Objectives: actual agent metrics; real deployment success/failure feedback;
operations limited to approved projects; one private/public agent protocol.
The agent initiates communication with the server. Do not expose Docker TCP API.

## Section 6: Success targets (not measured results)

| Area | v0.1 target | Evidence |
| --- | --- | --- |
| Host | One Ubuntu VM | Registered and active agent |
| Metrics | Actual CPU/RAM/disk | Comparison against OS readings |
| Deployment | One Nginx demo | HTTP response and Docker inspect |
| Lifecycle | Stop and start | Container state change |
| Safety | Unrelated containers untouched | Negative test |

## Sections 7–8: Users and permissions

Users are student operators, group observers, and the lecturer. v0.1 allows one
operator account or restricted demo access; authentication remains mandatory for
demos accessed by others and for all mutations. Viewer permissions are v0.2+:
view metrics but no deployment or lifecycle mutations. Neither role gets UI host
configuration changes or remote shell access. Full RBAC is deferred.

## Section 9: Scope

| Version | Included | Excluded |
| --- | --- | --- |
| v0.1 | One host, metrics, Docker inventory, deploy/start/stop Nginx | Multi-host, backups, cloud |
| v0.2 | Two hosts, host selection, unified monitoring | Advanced scheduler |
| v0.3 | Private/public managed hosts, secure agent | Automatic cloud VM creation |
| v1.0 | RBAC, audit, job history, backup/restore | Kubernetes, HA |

## Sections 10–11: Architecture and modules

Source direction: modular monolith, React/Vite frontend to FastAPI over HTTP(S),
authenticated outbound agent to FastAPI, agent to local Docker socket. SQLite may
serve v0.1; PostgreSQL is considered when concurrency/multi-host requires it.
Future hybrid connectivity uses Tailscale or end-to-end TLS.

| Module | v0.1 direction | Later development |
| --- | --- | --- |
| A Identity | Simple operator authentication | RBAC, sessions |
| B Control | API, command handling | Durable orchestration |
| C Data | SQLite, operation history | PostgreSQL, retention |
| D Agent | Heartbeat, telemetry, commands | Reconnect, credential lifecycle |
| E Infrastructure | Inspect, deploy, start/stop | Multi-host deployment |
| F Backup | Excluded | Restic, MinIO, restore drill |
| G Dashboard | Overview, host, demo app | Timeline, roles, alerts |

## Section 12: Deployment workflow

Select an approved Nginx template, validate host/permissions, execute Compose in
the designated namespace, verify Docker and HTTP state. Minimum operation states:
`QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `UNKNOWN`. Repeated requests cannot
blindly execute twice. Timeout does not prove failure: use `UNKNOWN` when results
remain unverified. Automatic stateful rollback is outside v0.1.

## Section 13: Functional requirements

| ID | Requirement | Priority/version |
| --- | --- | --- |
| FR-01 | Host online/offline | Must |
| FR-02 | Actual CPU/RAM/disk | Must |
| FR-03 | Managed container list | Must |
| FR-04 | Deploy approved Nginx template | Must |
| FR-05 | Start/stop demo | Must |
| FR-06 | Errors and operation feedback | Must |
| FR-07 | Do not modify non-demo containers | Must |
| FR-08 | Operation history | Should |
| FR-09 | Second host | v0.2 |
| FR-10 | Cloud managed host | v0.3 |
| FR-11 | Audit log and RBAC | v1.0 |
| FR-12 | Backup/restore | v1.0 |

## Section 14: Non-functional requirements

Security: no open Docker API or arbitrary shell; verify with negative tests.
Reliability: expose errors/offline state; test network disconnects. Portability:
Ubuntu local/cloud smoke tests in two environments at the appropriate milestone.
Usability: observed deployment from UI without CLI. Cost: no automatic paid resource
creation. Performance: record one-host dashboard latency rather than assuming it.

## Section 15: Data requirements

Initial entities: hosts (identity/status/last seen), latest metrics (host/time/CPU/
RAM/disk), templates (identity/name/revision/digest), operations (identity/host/type/
status/times), operation events (operation/time/sanitized message), agent credentials
(host/key hash/revocation time, if agent authentication is applied).

Use UUIDs, UTC time, explicit operation states, bounded metric retention, and no
plaintext secrets. Preserve identity/API contracts through migrations. The source
adds deployment targets and an attempt journal at v0.2+ to prevent duplication.
This digest does not define a database schema.

## Section 16: User flows

- Monitor: dashboard summary, agent telemetry, updated UI, stale indicator.
- Deploy: approved template, preflight, operation, approved Compose, verification,
  URL/status feedback.
- Stop/start: permission check, typed command, Docker action, refreshed state.
- Failure: agent disconnect or Compose error, error code/time, `FAILED`/`UNKNOWN`
  display, operator inspection.

## Section 17: API requirements (planned source endpoints)

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/v1/hosts` | List hosts |
| GET | `/api/v1/hosts/{id}/metrics` | Metrics |
| GET | `/api/v1/hosts/{id}/containers` | Managed inventory |
| GET | `/api/v1/templates` | Approved templates |
| POST | `/api/v1/deployments` | Create deployment |
| GET | `/api/v1/operations/{id}` | Operation status |
| POST | `/api/v1/containers/{id}/start` | Start managed demo |
| POST | `/api/v1/containers/{id}/stop` | Stop managed demo |
| POST | `/api/v1/agents/heartbeat` | Heartbeat |
| POST | `/api/v1/agents/operations/{id}/result` | Agent result |

Separate agent and browser namespaces; authenticate and validate all mutations.
Contracts need request/response schemas, 401/403/404/409/422/503 handling, operation
ID, timestamp, stable error codes, and HTTP 202 for asynchronous deployments.
These endpoints are not implemented; complete schemas remain to be specified.

## Section 18: UI requirements

Actual data, explicit stale/offline state, and distinct running/succeeded/failed/
unknown outcomes. Views: overview (counts/connectivity/latest metrics), host detail
(metrics/OS/agent version/last seen), Nginx demo (deploy/start/stop/status/URL),
operation detail (time/host/stage/result), and empty/error states for no host,
offline agent, stale metrics, or deployment failure.

## Section 19: Security requirements

Trust boundaries: browser/server and server/agent. No arbitrary shell. Allowlist
Compose projects, images, ports, and mounts; forbid privileged mode and host-root
mounts. No browser/network Docker socket access. Use unique revocable agent
credentials, never logged. Cross-network traffic requires HTTPS/WSS or a secure
private tunnel. Restrict control-plane access and authenticate operators.
Production DavidLab requires approval and rollback planning before any mutation.

## Section 20: Testing and demonstration

| ID | Scenario | Passing evidence |
| --- | --- | --- |
| AC-01 | Dashboard accessible | Screenshot and HTTP response |
| AC-02 | Correct metrics | OS comparison |
| AC-03 | Correct Docker inventory | Compare `docker ps` |
| AC-04 | Deploy Nginx | Running container and HTTP URL |
| AC-05 | Stop/start | State matches action |
| AC-06 | Agent offline | No false healthy UI |
| AC-07 | Unapproved template | Rejected request |
| AC-08 | Non-demo container | Unchanged |
| AC-09 | Failed operation | Error and operation ID |

Collect screenshots, Docker output, application URLs, and before/after evidence.
End-to-end proof matters; these tests have not been run in Phase 0.

## Section 21: Source milestones

M0: PRD/architecture approved by group and lecturer. M1/v0.1: single-host product
passing AC-01–09. M2/v0.2: verified deployments on two hosts. M3/v0.3: secure real
private/public demo. M4/v1.0: optional RBAC/audit/backup with recovery and policy
tests. Duration estimates await team assignments and lecturer timing.

The [roadmap](ROADMAP.md) maps the assignment's phases onto these milestones.

## Sections 22–23: Risks and future work

Risks include cloud registration failure, Docker privileges, laptop capacity,
disconnects, scope creep, single-member dependency, and unexpected costs. Mitigate
with local-first progress, isolated VMs/allowlists, limited concurrent VMs,
last-seen/stale status, bounded retries, frozen v0.1 scope, and cost review.

Future candidates: parallel/sequential deployments, durable reconciliation,
PostgreSQL, RBAC/audit/credential rotation, Restic/MinIO/restore/retention,
capability discovery, maintenance mode, Azure/OCI provisioning integrations, HA,
alerts, and advanced observability. These are not MVP implementation commitments.

## Section 24: Glossary

| Term | Meaning |
| --- | --- |
| Control plane | Central service accepting commands and exposing status |
| Managed host | Linux host managed through an agent |
| Agent | Host program for telemetry and restricted operations |
| Docker Compose | Declaration of container services and configuration |
| Hybrid cloud | Joint management of private and public infrastructure |
| Deployment | Applying an application to a target host |
| Heartbeat | Periodic agent connectivity signal |
| Preflight | Permission and readiness checks before execution |
| Acceptance criteria | Measurable completion conditions |

## Appendices A–C

**Demo:** view one online Ubuntu VM and actual metrics; deploy Nginx and observe
operation identity/state; verify success and open its real URL; stop/start and
verify availability; demonstrate non-demo protection.

**Changes from v1.0.0:** retain seven long-term modules; allow initial SQLite;
defer multi-deployment, full RBAC, and backup; target hybrid at v0.3 without blocking
v0.1; strengthen real-demo/negative-test evidence; remain vendor-agnostic without
requiring both Azure and OCI.

**Open questions from source:** Is public cloud mandatory for the final demo?
What are duration and presentation date? Who owns backend, agent, frontend, QA,
and documentation? Where will the control server run? Can a public VM be obtained
without payment? What campus network policy applies?
