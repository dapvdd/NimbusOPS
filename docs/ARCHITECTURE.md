# NimbusOps Architecture

## Status and authority

This is a **planned architecture**, derived from the supplied
[PRD v1.1](PRD.md), especially sections 3, 10–12, and 15–19. No component is
implemented. The source remains labeled draft/review required. This document
records its direction without asserting group or lecturer approval.

## Components and responsibility flow

```text
Dashboard -> Control Server -> Host Agent -> Docker Engine
```

| Component | Planned responsibility | Boundary |
| --- | --- | --- |
| Dashboard | Metrics, managed inventory, approved actions, operation feedback | Browser API only; no Docker access or credentials for agents |
| Control Server | Authenticate, validate, coordinate typed operations, store state/results | Modular monolith; separate browser and agent API namespaces |
| Host Agent | Heartbeat, actual telemetry, managed inventory, approved Compose execution | Runs on managed Ubuntu host; initiates server connection |
| Docker Engine | Execute approved application containers | Local socket only; no exposed Docker TCP API |

The responsibility arrow is not a transport design. Agent-to-server communication
is outbound and authenticated. The command delivery mechanism (for example polling
or a persistent outbound connection) is not yet chosen. Operation results and
telemetry flow back to the server; the dashboard reads server state.

## Technology and state

PRD direction: React/Vite frontend and FastAPI control server, with Docker
Engine/Compose on Ubuntu. SQLite may serve v0.1; PostgreSQL is deferred until
concurrency/multi-host requirements justify it. Agent language and all dependency
versions are pending.

PRD section 15 identifies hosts, latest metrics, approved templates, operations,
operation events, and agent credentials. It calls for UUID identifiers, UTC times,
explicit operation status, bounded metric retention, and no plaintext secret
storage. No database schema or migration is defined by this foundation.

## Communication and operation boundaries

1. The operator requests an approved action through the dashboard.
2. The server authenticates the caller, validates host/template/permission, and
   records a typed operation. No free-form shell command is accepted.
3. The agent obtains commands through its authenticated outbound connection and
   applies only allowlisted Compose projects, images, ports, and mounts.
4. Docker state and application HTTP response provide deployment evidence.
5. The server exposes operation identity, timestamps, stage, and sanitized results.

PRD operation states are `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, and `UNKNOWN`.
A timeout alone does not prove deployment failure. Duplicate requests require
checks before repeated execution. Exact delivery, retry, and reconciliation
contracts remain pending. Automatic stateful rollback is outside v0.1.

## Local-first topology

```text
Developer machine / isolated lab
  Browser -> Control Server + local development storage
                       ^
                       | authenticated outbound agent connection
  One isolated Ubuntu VM
    Host Agent -> local Docker socket -> approved Nginx demo (Phase 2)
```

Control-server placement is not yet decided: the developer machine or a separate
isolated lab machine can host it. Public cloud is not a prerequisite. No service,
port mapping, credentials, or VM is provisioned in Phase 0.

## Security assumptions and required controls

- The browser is untrusted; server-side authorization and validation apply to
  every mutation. Demos accessed by others require authentication.
- Each agent needs a unique, revocable credential that is never logged.
- Crossing networks requires HTTPS/WSS or a secure private tunnel. The choice of
  Tailscale versus end-to-end TLS remains open; neither is configured here.
- Access to a Docker socket grants powerful host capabilities; a local socket
  is not itself a least-privilege sandbox. Restrict operations through allowlists,
  forbid privileged containers and host-root mounts, and use an isolated VM.
- Only managed demo resources may be mutated. Negative tests must prove that
  unrelated containers are unaffected and unauthorized templates are rejected.
- Missing heartbeats and stale telemetry must remain visible, not appear healthy.
- Production DavidLab is outside authorized mutation scope. Future use requires
  explicit approval and a rollback plan.

These are design requirements, not claims of implemented security controls.

## Future hybrid topology

One control server will coordinate at least one private host and one public-cloud
VM using the same authenticated outbound agent protocol. Hosts may be in different
networks; Docker remains local to each host. Provider selection, access, budget,
and lecturer expectations must be confirmed first. A simulated fallback must be
labeled as such and cannot demonstrate real private-public acceptance.

Automatic cloud VM provisioning, Kubernetes, HA, and autoscaling are outside the
initial product. Backup and advanced RBAC follow core workflow validation.

## Decisions still pending

- Group/lecturer PRD approval, team ownership, schedule, and evaluation evidence.
- Control-server placement, host sizing, agent language, and dependency versions.
- Browser authentication/session method and agent enrollment/revocation process.
- Command delivery transport, retry limits, duplicate detection, and reconciliation.
- Metric units, sampling interval, stale/offline thresholds, and retention limits.
- Approved Nginx image/template revision, project namespace, ports, and mounts.
- Exact API schemas/errors and persistence details; no endpoint contract is finalized.
- Whether and when SQLite needs migration to PostgreSQL.
- Secure cross-network connectivity, provider/budget, and permitted cloud fallback.

Resolve decisions needed for each phase before implementing that phase; do not
turn these open questions into speculative Phase 0 code.
