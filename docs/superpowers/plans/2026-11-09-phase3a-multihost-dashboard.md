# Phase 3A — Multi-Host Dashboard & Safe Server Registry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Phase 2 top-nav dashboard into a multi-host console: sidebar shell, searchable server registry mixing real (backend) hosts and clearly-labeled simulated hosts, per-host Overview/Monitoring/Deployments/Activity tabs, safe add/remove of simulated hosts, truthful NOT-IMPLEMENTED states for real-host enrollment/removal.

**Architecture:** Frontend-only this phase. A `simRegistry` module (localStorage-persisted, key `nimbusops.sim-registry.v1`) owns simulated host state; `isSimulatedHostId(id)` (checks `sim-` prefix) is the single isolation primitive, enforced by a guard wrapper in `api/guard.ts` around every mutating API call. AppShell becomes a sidebar layout with a host-aware server list; new views render real or simulated host data through one interface; Phase 2 views keep working.

**Tech Stack:** React 18 + TypeScript + Vite + Tailwind + react-router v6; Vitest + Testing Library (stubbed-`fetch` pattern per existing tests).

**Spec:** `docs/superpowers/specs/2026-11-09-phase3a-multihost-dashboard-design.md`

## Global Constraints

- Frontend-only: no backend, agent, or Docker changes this phase.
- Simulated host IDs always `sim-` prefixed (`sim-<uuid4>`); registry persists under `localStorage["nimbusops.sim-registry.v1"]`; environments limited to `SIMULATED-DEV | SIMULATED-STAGING | SIMULATED-PROD` (never plain "PROD").
- A mutating API call (deploy/start/stop/container-state) with a `sim-` host must throw before `fetch` is invoked.
- Honesty: simulated hosts always show a visible SIMULATED badge; missing values render `—` (never 0); UTC timestamps.
- Preserve Phase 2 behavior: Overview and Applications keep working; `/hosts/:hostId` redirects to `/servers/:hostId`.
- Branch: `feat/phase3a-multihost-dashboard` from latest `origin/main`.

## Review Focus

1. localStorage unavailable or corrupt JSON — registry and settings reads must fall back to defaults, never crash (pinned: Task 1 corrupt-JSON test, Task 3 sidebar persistence test).
2. Deterministic metric generator with edge seeds must never produce NaN or out-of-range values (pinned: Task 1).
3. Simulated mutation leak-through — any code path passing a `sim-` host into a real POST must throw before fetch (pinned: Task 1 guard tests, Task 5 view-level isolation test).
4. Sidebar on mobile — off-canvas, Escape closes (pinned: Task 3).
5. API failure while a simulated host is selected — error state must render host-agnostic (pinned: Task 6).

### Task 1: simRegistry core — stable IDs, persistence, isolation guard (TDD)

**Files:**
- Create: `frontend/src/lib/simRegistry.ts`
- Create: `frontend/src/lib/simMetrics.ts`
- Create: `frontend/src/api/guard.ts`
- Test: `frontend/src/lib/__tests__/simRegistry.test.ts`

**Interfaces (authoritative):**
- `type SimEnvironment = "SIMULATED-DEV" | "SIMULATED-STAGING" | "SIMULATED-PROD"`
- `interface SimServer { id: string; name: string; environment: SimEnvironment; seed: number; created_at: string }`
- `interface SimRemovedEntry { id: string; name: string; removed_at: string }`
- `const SIM_ID_PREFIX = "sim-"`
- `function isSimulatedHostId(id: string): boolean` — true iff id starts with `sim-`.
- `function newSimId(): string` — `sim-` + crypto.randomUUID().
- `function listSimServers(): SimServer[]` — reads localStorage, corrupt JSON → `[]`.
- `function addSimServer(name: string, environment: SimEnvironment): SimServer` — trims name; blank or >64 chars throws RangeError; duplicate name (case-insensitive) throws Error.
- `function removeSimServer(id: string): void` — no-op if absent; records removed entry.
- `function listRemovedServers(): SimRemovedEntry[]`
- `function getSimSettings(): { sidebarCollapsed: boolean }` / `setSimSettings(patch)` — corrupt → defaults.

**Steps:**
- [ ] 1. Write failing tests in `simRegistry.test.ts`: (a) `addSimServer(" demo-1 ", "SIMULATED-DEV")` returns server with name `demo-1`, id matching `/^sim-/`, seed being an integer; (b) blank/whitespace name throws; (c) name of 65 chars throws; (d) duplicate name different case throws; (e) `removeSimServer` moves entry to removed list with `removed_at`; (f) corrupt localStorage JSON returns `[]` and does not throw; (g) `isSimulatedHostId("sim-abc")` true, `isSimulatedHostId("3f1c...uuid")` false.
- [ ] 2. Run `npx vitest run src/lib/__tests__/simRegistry.test.ts` — expected FAIL (module not found).
- [ ] 3. Implement `simRegistry.ts` per interfaces above; every read wrapped in try/catch → defaults.
- [ ] 4. Implement `simMetrics.ts`: `function simMetricsFor(server: SimServer, at: Date): LatestMetrics` — deterministic pseudo-random from `seed`+`id` hash, time-drifting sine, all values in plausible ranges (CPU 2–92%, mem/disk < 95%), total_bytes fixed per seed (e.g. 8/16/32 GiB), `recorded_at` = `at` ISO. No Math.random.
- [ ] 5. Implement `api/guard.ts`: `export function assertRealHost(hostId: string): void` — throws `Error("Refusing to send simulated host to real API")` if `isSimulatedHostId(hostId)`.
- [ ] 6. Run tests — PASS. Commit `feat: simulated host registry with stable IDs and persistence`.

### Task 2: API client isolation — mutations refuse simulated hosts (TDD)

**Files:**
- Modify: `frontend/src/api/client.ts` (wrap `deploy`, `startApp`, `stopApp`; `getContainerState` may stay read-only but must be called only after a real-host check in views)
- Test: `frontend/src/api/__tests__/client.guard.test.ts`

**Interfaces:**
- Consumes: `assertRealHost` from Task 1.
- Produces: unchanged signatures; `api.deploy("<sim-...>", ...)` rejects with ApiFailure kind `"http"`, status 400, message containing "simulated" — before any fetch.

**Steps:**
- [ ] 1. Failing test in `client.guard.test.ts`: stub `fetch` with `vi.fn()`; `await expect(api.deploy("sim-abc", "nginx-demo")).rejects.toThrow(/simulated/i)` and assert `fetch` was never called. (start/stop are guarded at view level — tested in Task 5, since the client only receives a deploymentId.)
- [ ] 2. Run — FAIL (no guard).
- [ ] 3. Implement: in `deploy`, call `assertRealHost(hostId)` first; throw `ApiFailure("http", "Simulated hosts cannot run real deployments.", 400)`. Leave `startApp`/`stopApp` unchanged; view-level guard in Task 5 covers them.
- [ ] 4. Run — PASS. Commit `feat: block simulated hosts from real deploy endpoint`.

### Task 3: Host registry model — one interface over real + simulated hosts

**Files:**
- Create: `frontend/src/lib/hostRegistry.ts`
- Test: `frontend/src/lib/__tests__/hostRegistry.test.ts`

**Interfaces:**
- Consumes: `api.listHosts()`, `listSimServers`, `simMetricsFor`, `isSimulatedHostId` (Task 1).
- Produces:
  - `interface UnifiedHost { id: string; name: string; environment: string; simulated: boolean; status: "ONLINE"|"STALE"|"OFFLINE"; latest: LatestMetrics | null; cores: number|null; totalMemoryBytes: number|null; platform: string|null; agentVersion: string|null; lastSeenAt: string|null; lastTelemetryAt: string|null; enrolledAt: string; isRevoked: boolean }`
  - `function mergeHosts(real: Host[], sim: SimServer[], at: Date): UnifiedHost[]` — real hosts → environment `"PRODUCTION"`; sim → their SimEnvironment; sim status always `"ONLINE"` with `simMetricsFor(server, at)`; sim `enrolledAt` = `created_at`.
  - `function findHost(hosts: UnifiedHost[], id: string): UnifiedHost | undefined`

**Steps:**
- [ ] 1. Failing tests: (a) merge of one real host + one sim server yields 2 unified hosts, sim one has `simulated: true`, environment starts with `SIMULATED-`, status `ONLINE`, metrics present and finite; (b) real host environment is `PRODUCTION`; (c) empty inputs → empty array.
- [ ] 2. Run — FAIL. 3. Implement. 4. Run — PASS. 5. Commit `feat: unified host model over real and simulated hosts`.

### Task 4: Sidebar shell (AppShell → sidebar layout)

**Files:**
- Modify: `frontend/src/components/AppShell.tsx` (rewrite layout; keep health poll + UTC clock)
- Create: `frontend/src/components/Sidebar.tsx`, `frontend/src/components/ServerList.tsx`
- Modify: `frontend/src/App.tsx` (routes: `/`, `/servers`, `/servers/:hostId`, `/deployments`, `/activity`, `/settings`, redirect `/hosts/:hostId` → `/servers/:hostId`)
- Test: `frontend/src/components/__tests__/sidebar.test.tsx`

**Interfaces:**
- Consumes: `mergeHosts`, `api.listHosts`, `getSimSettings/setSimSettings` (sidebar collapsed), `isSimulatedHostId`.
- Produces: `AppShell` now renders sidebar + main region; `Sidebar` props `{ collapsed, onToggle }`; `ServerList` props `{ hosts: UnifiedHost[]; selectedId: string | null; query: string; onQuery: (q: string) => void }`; server item navigates to `/servers/:hostId`.

**Steps:**
- [ ] 1. Failing test `sidebar.test.tsx`: (a) renders brand "NimbusOps" and nav items Overview, Servers, Deployments, Activity, Settings (role="navigation"); (b) given hosts incl. one sim, server list shows sim name with visible text "SIMULATED"; (c) search input filters by name substring case-insensitive; (d) collapsed state from `getSimSettings().sidebarCollapsed`, toggle calls `setSimSettings` and persists (reload via re-render reads new value); (e) Escape key closes the mobile drawer (mock `matchMedia` <768px path); (f) `/hosts/xyz` route redirects to `/servers/xyz`.
- [ ] 2. Run — FAIL. 3. Implement Sidebar (fixed 256px, collapse to 64px icon rail, Tailwind; mobile off-canvas with backdrop, `aria-label="Primary"` nav, focus management). 4. Implement ServerList (search box with `aria-label="Search servers"`, items: status dot + name + env badge). 5. Rewrite AppShell layout, keep `HealthDot` logic. 6. Update App.tsx routes incl. redirect. 7. Run full `npm test` — existing view tests must still pass (stub fetch as before); fix regressions only. 8. Commit `feat: sidebar shell with server list navigation`.

### Task 5: Server registry view + Add/Remove flows

**Files:**
- Create: `frontend/src/views/Servers.tsx`, `frontend/src/components/AddServerDialog.tsx`, `frontend/src/components/RemoveServerDialog.tsx`
- Test: `frontend/src/views/__tests__/servers.test.tsx`

**Interfaces:**
- Consumes: `mergeHosts`, `addSimServer/removeSimServer/listRemovedServers`, `assertRealHost` (for the real-host removal refusal), `isSimulatedHostId`.
- Produces: registry page at `/servers`; dialog components reusable; sim host cards navigate to `/servers/:hostId`.

**Steps:**
- [ ] 1. Failing tests: (a) renders real + sim cards, sim cards show "SIMULATED" badge and environment; (b) search filters; (c) Add Server → dialog offers two options; choosing "Simulated demo server", entering name "demo-web", picking "SIMULATED-DEV", submitting → card appears (and `fetch` never called); (d) blank name submit shows inline validation error; (e) Add dialog's "Existing server" option shows NOT IMPLEMENTED panel with truthful copy and disabled submit; (f) Remove on sim host → confirm dialog → card gone, entry appears in removed list; (g) Remove on real host (DavidLab) → dialog states removal NOT IMPLEMENTED, confirm disabled, DavidLab name shown; (h) removing DavidLab by any path never calls fetch.
- [ ] 2. Run — FAIL. 3. Implement Servers view (cards, search, empty state "No servers match"). 4. Implement AddServerDialog (two-tab or radio: Simulated / Existing-real; real → NOT IMPLEMENTED panel, no network calls). 5. Implement RemoveServerDialog (sim → confirm type-to-confirm optional, simple confirm; real → NOT IMPLEMENTED, disabled). 6. Run full suite — PASS incl. regressions. 7. Commit `feat: server registry view with safe add/remove flows`.

### Task 6: Host views — Overview / Monitoring / Deployments / Activity tabs

**Files:**
- Create: `frontend/src/views/HostOverview.tsx` (identity + status + current metrics; reuse HostDetail panels)
- Create: `frontend/src/views/HostMonitoring.tsx` (reuse HistoryTable; for sim hosts show generated history)
- Create: `frontend/src/views/HostDeployments.tsx`, `frontend/src/views/HostActivity.tsx`
- Create: `frontend/src/views/ServerDetail.tsx` (tab container at `/servers/:hostId`)
- Modify: `frontend/src/views/Applications.tsx` (minimal: fetch by real host only, skip sim; see step 5)
- Test: `frontend/src/views/__tests__/serverDetail.test.tsx`

**Interfaces:**
- Consumes: `mergeHosts`/`findHost`, `simMetricsFor`, `api.*` (Task 1–4).
- Produces: `ServerDetail` with tab param `?tab=` defaulting `overview`; sim host renders entirely from registry+generator (zero fetches); real host renders from API (existing behavior preserved).

**Steps:**
- [ ] 1. Failing tests (stub fetch): (a) `/servers/<real-uuid>` renders API host data with PRODUCTION badge, Overview tab active; (b) `/servers/sim-abc` renders sim name, SIMULATED badge, generated metrics, and **fetch not called**; (c) tabs Monitoring/Deployments/Activity switch content; (d) unknown id → "Server not found" panel; (e) sim host Deployments tab shows honest empty state ("Simulated hosts have no real deployments") and Deploy button disabled; (f) sim host Activity tab shows only local registry events (added/removed); (g) real host Deployments tab still lists API applications (regression); (h) real-host API failure renders the shared error panel with retry, host-agnostic (no crash when a sim host is later selected).
- [ ] 2. Run — FAIL. 3. Implement ServerDetail + four tab views; sim branch never imports api mutation calls. 4. Implement generated history for sim Monitoring (30 points, 5-min interval). 5. Applications.tsx: filter `mergeHosts(...).filter(h => !h.simulated)` for its host selector; if selected host is sim, show honest disabled state. 6. Run full suite — PASS. 7. Commit `feat: per-host overview, monitoring, deployments, activity views`.

### Task 7: Fleet pages — Deployments / Activity / Settings + polish

**Files:**
- Create: `frontend/src/views/Deployments.tsx` (all real applications; sim section labeled "Simulated hosts have no deployments"), `frontend/src/views/Activity.tsx` (real ops feed from API + registry events, visually separated), `frontend/src/views/Settings.tsx` (theme note, registry reset button with confirm)
- Modify: `frontend/src/components/StatusBadge.tsx` (add SIMULATED variant) if needed
- Test: `frontend/src/views/__tests__/fleet.test.tsx`

**Steps:**
- [ ] 1. Failing tests: (a) Deployments page lists API apps with host names and a labeled sim section; (b) Activity page merges real operations and registry events with separate section headings; (c) Settings shows registry size and Reset removes all sim servers after confirm; (d) each page's error and empty states render.
- [ ] 2. Run — FAIL. 3. Implement the three views. 4. Run full suite — PASS. 5. Commit `feat: fleet deployments, activity, and settings pages`.

### Task 8: Docs, screenshots, full verification

**Files:**
- Create: `docs/PHASE3A_NOTES.md` (architecture notes: stable-ID contract, isolation guard, enrollment design for real hosts — one-time expiring tokens, operator-approved, revocation-before-unregister; known limitations)
- Create: `docs/PHASE3A_VERIFICATION.md` (commands, results, evidence)

**Steps:**
- [ ] 1. Run full frontend suite `npm test`; `npm run build` (tsc -b && vite build) — both must pass.
- [ ] 2. Run full Python suite from repo root (`.venv\Scripts\python -m pytest`) — must pass unchanged (no backend edits).
- [ ] 3. Screenshots: start `vite dev`, use Playwright to capture sidebar, Servers page with sim host, host detail tabs, Add dialog, Remove confirm. Save under `docs/screenshots/phase3a/`.
- [ ] 4. Write both docs; include known limitations (per-browser sim state, no real enrollment, no unregister, single-operator).
- [ ] 5. Commit `docs: phase 3A notes and verification report`.
- [ ] 6. Final regression: `npm test`, `npm run build`, `pytest` all green; report summary. Do NOT deploy; stop for approval per brief.


