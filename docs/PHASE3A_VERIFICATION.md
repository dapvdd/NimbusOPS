# Phase 3A verification report

Date: 2026-11-10 · Branch: `feat/phase3a-multihost-dashboard` · Base: `main` @ 9a2095a

## Delivered (frontend only)

- Persistent sidebar shell (Overview, Servers, Deployments, Activity, Settings),
  collapsible rail, host-aware server list with search and status dots.
- Servers registry: real hosts from `GET /api/v1/hosts`; simulated hosts from
  browser-local registry (`nimbusops.sim-registry.v1`), labelled SIMULATED.
- Simulated add/remove flows with confirmation; local removal history retained.
- Per-host tabs at `/servers/:hostId`: Overview, Monitoring, Deployments,
  Activity; simulated hosts never call the API and show synthetic-sample labels.
- Add Existing Server and real Remove Server show truthful NOT IMPLEMENTED.
- Stable identity: real UUID from API; simulated `sim-<uuid>`; display name edits
  do not change IDs. Hostname is not used as a routing identity.
- Isolation: request layer rejects any `sim-` resource ID or simulated `host_id`
  before `fetch`, covering deploy/start/stop/metrics/operation/container-state.

## Commands run and results

| Check | Command | Result |
|---|---|---|
| Frontend tests | `npm.cmd test` (in `frontend/`) | 8 files, **37 passed**, exit 0 |
| TypeScript + Vite build | `npm.cmd run build` | `tsc -b` clean, built in 2.29s, exit 0 |
| Python suite | `.\.venv\Scripts\python.exe -m pytest -q` | **96 passed**, 3 pre-existing deprecation warnings, exit 0 |

New tests: `simRegistry.test.ts` (persistence, validation, corrupt storage,
real-ID removal refusal), `client.guard.test.ts` (no fetch for simulated IDs),
`servers.test.tsx` (add/remove, SIMULATED labelling, NOT IMPLEMENTED enrollment,
API-failure resilience), `console.test.tsx` (sidebar host selection + search,
simulated tab navigation with zero simulated-ID requests), `activity.test.tsx`
(host-scoped operations). Existing Phase 2 tests unchanged and passing.

## Screenshots

`docs/screenshots/phase3a/`: `01-servers.png`, `02-add-server.png`,
`03-simulated-host.png`, `04-remove-confirm.png`, `05-overview.png`.
Captured headless Chrome 1440×1100 against local Vite dev + local backend with a
seeded browser-local simulated registry.

## Not done / not verified

- No backend, agent, Docker, systemd, firewall, SPECTRA, or reverse-proxy changes.
- No deployment to `david-lab`; no live host contacted during this work.
- Real enrollment/unregister remain NOT IMPLEMENTED; see `PHASE3A_NOTES.md`.
- Mobile drawer (Escape/backdrop) is **not** implemented; narrow screens wrap the
  sidebar above content. The earlier plan item for drawer behaviour is deferred.
- Sidebar collapse state is session-local, not persisted.
- Simulated Monitoring shows current synthetic samples, not a history chart.
- Activity shows only the latest operation per deployment supplied by the API.
- Screenshots are visual evidence only; interaction correctness is evidenced by
  the automated tests above.
