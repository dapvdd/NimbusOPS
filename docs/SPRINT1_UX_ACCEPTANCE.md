# Sprint 1 — UX Perfection Acceptance

Branch: `sprint/ux-perfection`. Commits in this sprint:

| Commit | Slice |
|---|---|
| `baee82e` … `f3a8809` | Pre-sprint credentials/re-enroll groundwork (preserved) |
| `699883e` | Backend: effective host status, agent mode, lifecycle guards |
| `49029a9` | Agent: one-shot re-enroll and credential-file application |
| `d770386` | Frontend: design primitives, code-aware errors, cookie-only auth |
| `dc87580` | Frontend: zero-friction enrollment wizard |
| `7722429` | Frontend: host lifecycle, history, and service panels |
| `dc6342e` | Frontend: unified dashboard, settings, and status consumers |
| _this commit_ | Frontend: remove simulated registry and finalize verification |

## What shipped

- **Honest lifecycle.** Host status is computed by the backend (`effective_status`), with
  `REVOKED` terminal. The UI never renders a revoked host as offline and never offers
  reconnect with revoked credentials.
- **Credential lifecycle.** Rotate, re-enroll (single-use bootstrap token), and revoke are
  real authorized operations. Re-enroll polling confirms via `credential_version` +
  `is_revoked=false` + `last_seen_at` — never by parsing event strings.
- **Cookie-only browser auth.** The browser session uses HttpOnly cookies; session tokens are
  never exposed to JavaScript or `localStorage`. CSRF tokens remain required for
  cookie-authenticated mutations. Bearer auth remains for legitimate non-browser clients.
- **Unified dashboard.** KPI counts (registered/online/stale/offline/revoked/awaiting),
  a needs-attention queue with one resolving link per row, an attention-sorted fleet table,
  and the last five real operations. The “all systems operational” banner appears only when
  `/health` is ok AND nothing needs attention.
- **Settings.** Account + sign out, control-plane health/readiness with 503-as-data and
  concrete recovery steps (no restart button), and a copyable deployment reference.
- **Role-correct actions.** VIEWER never receives deploy/start/stop or enrollment controls;
  they are absent from the DOM, not merely disabled.
- **Simulation removed.** `lib/simRegistry.ts` and its tests are deleted; no UI consumer
  imports it. The server-side `SIMULATED_HOST_REJECTED` guard and the client
  `assertNotSimulated` mutation guard remain as defense in depth.
- **One host URL.** `/hosts/:hostId` redirects to `/servers/:hostId`.

## Verification evidence (this workspace)

All four gates were run on the final slice:

| Gate | Result |
|---|---|
| `pytest` | 334 passed, 1 skipped |
| `npm test -- --run` | 128 passed (21 files) |
| `npx tsc -b` | clean |
| `npx vite build` | clean (67 modules) |
| Grep gate `simRegistry\|addSimServer\|listSimServers\|listRemovedServers\|SIMULATED-` | no matches in `frontend/src` |

Key behaviors are pinned by tests, including:

- revoked host counted in `count-revoked` and never `count-online`; “Needs attention” links
  to `/servers/:id`;
- all-clear absent while any attention item exists, present only with healthy `/health`;
- readiness 503 rendered as degraded data with recovery steps and no restart control;
- VIEWER has no deploy/start/stop in the DOM; REVOKED shows “re-enroll required”;
- legacy `/hosts/:id` redirect;
- `sim-*` ids are refused before any request is sent.

## Data-compatibility check

The demo DB at `demo-multihost-rc2/backend/nimbusops.db` is schema-only (0 hosts, 0
operators, 0 telemetry, 0 operations), so it cannot evidence a populated upgrade. A
populated legacy local copy was used instead, read-only:

- source: `C:\Users\user\Development\NimbusOPS\backend\nimbusops.db` (never modified)
- migrated copy: `%TEMP%\opencode\nimbusops-compat\compat.db`
- startup migration (`create_all()` + `upgrade_phase3b()`)

Result:

```json
{
  "before_counts": { "hosts": 2, "telemetry": 264, "managed_deployments": 1, "deployment_operations": 9 },
  "after_counts":  { "hosts": 2, "telemetry": 264, "managed_deployments": 1, "deployment_operations": 9 },
  "hosts": 2,
  "problems": [],
  "additive_new_tables": [
    "bootstrap_tokens", "host_events", "inventory_snapshots",
    "operator_sessions", "operators", "phase3b_migration_marker"
  ],
  "additive_new_columns": [
    "hosts.agent_mode", "hosts.enrollment_status", "hosts.docker_enabled",
    "hosts.environment", "hosts.credential_version",
    "hosts.previous_token_hash", "hosts.previous_token_expires_at",
    "deployment_operations.claim_generation", "deployment_operations.timeout_at"
  ]
}
```

Row counts and host identities are unchanged; every schema change is additive. The live DB
was never opened.

## Not verified here

- **Real systemd install / agent upgrade** on a remote host.
- **Docker deployment acceptance** (no Docker engine in this workspace).
- **Soak / long-running polling** behavior.
- **The optional Playwright E2E harness** (`docs/E2E.md`): Playwright is not installed in
  this workspace, so it was written and committed but not executed.
- **The deployed DavidLab instance**: this branch was not deployed; do not infer runtime
  state from this document.

Push, merge, and deploy remain separate approved actions.
