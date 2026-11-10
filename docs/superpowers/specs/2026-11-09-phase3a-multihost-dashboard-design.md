# Phase 3A — Multi-Host Dashboard & Safe Server Registry (Design)

Date: 2026-11-09 · Base: main @ 9a2095a (post PR #3) · Status: approved by task brief

## Intent

Turn the Phase 2 single-host top-nav dashboard into a multi-host infrastructure
console: persistent sidebar navigation, a searchable server registry with real
(DavidLab) and clearly-labeled simulated hosts, per-host Overview / Monitoring /
Deployments / Activity views, and safe add/remove flows. Phase 2 monitoring and
Docker functionality must keep working unchanged.

## Goals / non-goals / anti-goals

- Goals: sidebar shell; server cards (name, environment, status, metrics
  summary); search; selected-host navigation; simulated host add/remove;
  truthful NOT IMPLEMENTED states for real-host enrollment/unregister.
- Non-goals (this phase): any backend mutation, real enrollment endpoint,
  deployment to david-lab, agent changes.
- Anti-goals: mock data presented as real; fake hosts reaching the backend or
  telemetry tables; simulated IDs reaching Docker/agent mutation endpoints.

## Constraints (from repo inspection)

- Backend is already multi-host-shaped (`hosts` PK `id` UUID string; per-host
  telemetry, deployments, operations) but has **no host CRUD API** — enrollment
  is the only creation path. Frontend-only simulated registry therefore needs
  zero backend change.
- Existing frontend: React 18 + TS + Vite + Tailwind + react-router v6; views
  own their state; tests = Vitest + Testing Library with stubbed global `fetch`
  (`views.test.tsx`, `applications.test.tsx`); build = `tsc -b && vite build`.
- Honesty rules: `docs/ARCHITECTURE.md:133` (simulated fallback must be
  labeled) and `docs/PRD-v2.0.md:63` (simulated multi-host allowed, labeled).

## Approaches considered

1. **Frontend-only simulated registry, localStorage-persisted** (chosen — the
   task pre-authorizes exactly this). Zero backend risk; simulated state dies
   with the browser profile, never touches telemetry tables. Trade-off: state
   is per-browser, which is *correct* for demo data.
2. Backend `simulated_hosts` table + API. Rejected for 3A: backend mutation
   requires approval, and demo hosts in any server-side store invite real/mock
   contamination; revisit only if cross-browser demo state is ever needed.
3. URL-param-only mock (no persistence). Rejected: add/remove flows become
   meaningless; unstable host identity across reloads violates the stable-ID
   contract requirement.

## Decisions (my calls, flagged)

- **Stable host ID contract:** simulated host IDs are `sim-<uuid4>` — the
  `sim-` prefix can never collide with real UUID PKs, survives hostname edits,
  and gives code/tests a one-glance isolation check. Real hosts keep backend
  UUIDs. Rename updates display name only; ID never changes.
- **Isolation guard:** single `isSimulatedHostId(id)` helper + a mutation
  wrapper that throws if a `sim-` ID is ever passed to a real API POST
  (deploy/start/stop/container-state). Views check it before any call. Tests
  assert fetch is never called with `sim-` IDs on mutation endpoints.
- **Registry shape:** `SimServer { id, name, environment, created_at,
  seed }` in `localStorage["nimbusops.sim-registry.v1"]`; metrics are
  generated deterministically from `seed + id` (plausible, time-drifting) and
  rendered with the same honesty rules (dash for missing, UTC).
- **Environment badges:** real host = PRODUCTION (or its known context);
  simulated = SIMULATED badge, amber, plus a "Simulated" ribbon in every host
  view and a visible note in Deployments/Activity that no real operations occur.
- **Routes:** `/` (fleet Overview), `/servers` (registry), `/servers/:hostId`
  (tabs: overview · monitoring · deployments · activity),
  `/deployments` (all real apps; simulated section labeled),
  `/activity` (real ops feed), `/settings`. Existing `/hosts/:hostId`
  redirects to `/servers/:hostId` so old links keep working.
- **Add Server:** modal with two clearly separated options —
  (a) "Existing server (real)": truthful NOT IMPLEMENTED panel explaining the
  future token-based enrollment, disabled until backend support lands;
  (b) "Simulated demo server": name + environment picker, works fully
  client-side.
- **Remove Server:** simulated → confirm dialog → registry removal (audit
  trail: `removed_at` list kept in the registry file for the Activity view).
  Real hosts (DavidLab) → NOT IMPLEMENTED; removal button disabled with the
  reason ("unregister requires credential revocation — Phase 3 backend").
- **Sidebar:** collapsible (persisted), keyboard-accessible, mobile
  off-canvas; keeps health poll + UTC clock from the current AppShell.

## What's left to the builder

- Exact Tailwind visual treatment for sidebar/cards (premium dark console).
- Component split for the four host tabs; reuse existing HostDetail chart code
  for the monitoring tab.
- Test file organization mirroring existing `__tests__` conventions.

## Stop-for-approval gates (per task brief)

1. Any backend registry/enrollment code → separate approval.
2. Any deployment (Vite build output to a server, david-lab changes) → separate
   approval.

## Verification plan

Vitest suite (new: registry, isolation, host selection, add/remove, states;
regression: existing views/applications tests), `tsc -b && vite build`,
full pytest run untouched. Screenshots via Playwright against `vite dev`.
