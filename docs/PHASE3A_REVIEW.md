# Phase 3A visual and independent review

Date: 2026-11-10
Commit under review: `9516e91` on `feat/phase3a-multihost-dashboard`
Scope: frontend-only review. No backend, Docker, systemd, firewall, SPECTRA, or
production deployment was modified.

## Verdict

Phase 3A is functionally sound and isolated from real infrastructure. Three
confirmed defects were found and fixed (see Important). No Critical defect was
confirmed. Remaining items are Minor or Deferred.

The five screenshots were reviewed by a vision-capable model
(`9router/kr/claude-sonnet-4.5`), which returned `VISION_OK` and cited
screen-specific content. Two other vision attempts failed for provider reasons
(`VISION_UNAVAILABLE`, invalid model ID, upstream `ECONNREFUSED`), so the visual
review rests on that single successful pass plus code inspection.

## Findings

### Critical

None confirmed.

### Important — fixed in this review

**I1. Request guard could be bypassed by case or percent-encoding in a JSON
`host_id`, and malformed encoding threw a raw `TypeError`.**
`frontend/src/api/client.ts` only checked the raw body value with a
case-sensitive `startsWith("sim-")`. A caller passing `sim%2Dabc`, `SIM-abc`,
or a malformed `%E0%A4%A` reached `fetch` instead of being refused with an
`ApiFailure`.
Fixed: the guard now decodes each path segment and the body `host_id`, compares
case-insensitively, and rejects undecodable identifiers with
`Invalid resource identifier.` before any network call.
Tests: `client.guard.test.ts` — plain IDs across deploy/start/stop/host/metrics/
operation/container-state, case-varied IDs, encoded body `host_id`, malformed ID.

**I2. Registry did not deduplicate stored IDs.**
`frontend/src/lib/simRegistry.ts` filtered invalid entries but kept duplicate
`sim-` IDs from tampered or legacy storage. Duplicates produced duplicate React
keys and made "Remove" ambiguous (removing one ID silently removed every copy).
Fixed: `read()` now keeps the first valid entry per ID for both `servers` and
`removed`.
Tests: `simRegistry.test.ts` — duplicate IDs, tampered entries, removal with a
duplicate present, corrupt JSON, invalid names, refusal to remove real IDs.

**I3. "Overview" and "Monitoring" tabs rendered identical content.**
For real hosts both tabs rendered the full `HostDetail`; for simulated hosts both
rendered the same synthetic metrics. The tab bar promised navigation that did not
change anything.
Fixed: `HostDetail` accepts `view?: "overview" | "monitoring"`. Monitoring shows
metrics and recent telemetry without the identity/connectivity panels; Overview is
unchanged. Simulated Monitoring adds "Historical telemetry is not simulated."
Test: `console.test.tsx` — Monitoring hides "Enrolled at" and shows "Recent
telemetry"; switching to Overview restores "Enrolled at".

### Minor — open

- **M1. Remove confirmation prose is clear but carries no SIMULATED badge.**
  The dialog says "This removes only the browser simulation. Local removal history
  is retained," which is accurate; an explicit badge would reinforce it. Not
  changed to keep the reviewed screenshot valid.
- **M2. "Existing server" reveals NOT IMPLEMENTED only after selection.**
  The toggle is visible but has no pre-click hint that enrollment is unavailable.
- **M3. Tabs are not fully wired for assistive technology.**
  `role="tab"`/`aria-selected` exist, but there is no `aria-controls`, tabpanel
  labelling, or arrow-key navigation.
- **M4. Duplicate empty-state copy on the Servers page.**
  A non-matching search can show both "No real servers registered" and
  "No servers match your search."
- **M5. Sidebar collapse is session-local** and not persisted across reloads.
- **M6. `save()` can throw `QuotaExceededError`.** The message is surfaced as a
  form error, but it is not worded for storage exhaustion.

### Deferred

- Mobile drawer with backdrop/Escape; narrow screens wrap the sidebar above
  content (documented in `PHASE3A_VERIFICATION.md`).
- Simulated monitoring history chart (current synthetic samples only).
- Complete audit history (Activity shows the latest operation per deployment).
- Real enrollment and unregister (NOT IMPLEMENTED by design; see
  `PHASE3A_NOTES.md`).
- Shape/icon differentiation for status dots beyond the existing text badges.

## Visual review notes and rejected claims

The vision reviewer marked amber text on the dark surface as a Critical contrast
failure. Measured against the actual tokens, `amber-300` `#fcd34d` on `ink-950`
`#0b0f14` is **≈13.4:1**, which passes WCAG AA and AAA for normal text. That
finding was rejected rather than "fixed"; no colour changes were made.

The reviewer also noted that status dots rely on colour alone. Every simulated
entry also carries a `SIMULATED` text badge and a separate section heading, so the
dot is not the sole differentiator. Shape differentiation is recorded as Deferred.

The reviewer observed that the global Overview does not list simulated hosts.
This is intentional: the global Overview summarises real infrastructure, while the
Servers page is the simulation registry. Recorded as by design, not a defect.

Screenshots remain valid evidence for the five captured states. The Monitoring
change is not covered by a screenshot and is verified by test.

## Isolation evidence

- `client.guard.test.ts` asserts `fetch` is never called for simulated IDs across
  deploy, start, stop, host, metrics, operation, and container-state.
- `console.test.tsx` asserts that direct navigation to `/servers/<sim-id>`,
  `/servers/<URL-encoded sim-id>`, and the legacy `/hosts/<sim-id>` renders the
  simulated view without sending the ID to the API.
- Simulated Deployments/Activity branches render static text, not operational
  controls; no deploy/start/stop UI is reachable for a simulated host.

## Regression and build results

| Check | Command | Result |
|---|---|---|
| Frontend tests | `npm.cmd test` (`frontend/`) | 8 files, **45 passed**, exit 0 |
| Production build | `npm.cmd run build` | `tsc -b` clean, Vite built, exit 0 |
| Backend/agent suite | `.\.venv\Scripts\python.exe -m pytest -q` | **96 passed**, exit 0 |

Phase 2 coverage (`views.test.tsx`, `applications.test.tsx`) still passes, so
real-host monitoring and deployment workflows are not regressed.

## Working tree

Modified only frontend files:
`api/client.ts`, `api/client.guard.test.ts`, `lib/simRegistry.ts`,
`lib/simRegistry.test.ts`, `views/HostDetail.tsx`, `views/ServerDetail.tsx`,
`views/__tests__/console.test.tsx`.

Unrelated untracked files preserved untouched:
`docs/NIMBUSOPS_DEMO_READY.md`, `docs/NIMBUSOPS_DEMO_RESULTS.md`,
`docs/STAGE_A_DAVIDLAB_AUDIT.md`, `frontend/src/lib/format.test.ts`.

Fixes are **not committed, not pushed, no PR, not deployed**. Approval is required
before any of those steps.
