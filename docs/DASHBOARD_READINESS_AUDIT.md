# NimbusOps dashboard functional readiness — 2026-11-22

## Verdict: PARTIALLY READY

The dashboard can honestly demonstrate navigation, authentication UI, empty
fleet/application/history states and configured API-driven views. It is **not**
verified as a complete live infrastructure management demo. Passing component
tests are not live host/Docker/Ubuntu acceptance. No production deployment occurs.

Development branch: `dev/dashboard-functional-audit`, branched from the existing
isolated worktree's detached HEAD. Pre-existing acceptance evidence and changes
were preserved, not included in these repairs.

## Evidence levels

- **UI**: Vitest/Testing Library, real components and client with mocked fetch.
- **API**: pytest with disposable SQLite fixtures and FastAPI TestClient.
- **HTTP**: existing Python loopback integration tests, real agent client and
  backend code; not a deployed Ubuntu service or real Docker execution.
- **Browser**: headless Chromium against local Vite with explicitly intercepted
  fixture API; no operational writes, no live backend contract proof.
- WORKING means verified at the stated level, not unrestricted operational approval.

## Route and control matrix

| Route / surface | Status | Verified actions and evidence | Limitations / unknowns |
|---|---|---|---|
| `/login` | WORKING (UI/API/Browser) | Username/password form, anonymous redirect, cookie restore/logout/CSRF, expired-session rejection, invalid credentials, VIEWER restrictions. `auth.test.tsx`, `test_browser_auth.py`; browser login/logout smoke. | Browser smoke uses fixture responses; no full browser-to-live-API login performed this session. |
| Shell / primary navigation | WORKING (UI/Browser) | Overview, Servers, Deployments, Activity, Settings navigation; host selection and sidebar collapse in `console.test.tsx`; API degraded indicator in `appshell.health.test.tsx`. | Supplementary sidebar failure is silent; no full responsive/keyboard audit. |
| `/` Overview | PARTIAL | API fleet counts, missing-metric dashes, revoked/stale/offline labels, empty/error states and periodic refresh; late failed refresh no longer retains all-clear. `views.test.tsx`; browser empty fleet. | No automatic provisioning job feed; unresolved jobs are not part of all-clear calculation. Token list bounded to 50; expired-token guidance not provisioning-specific. No real fleet observed. |
| `/servers` | PARTIAL | Name search, status/environment filters, awaiting rows, refresh, Add Server navigation, typed unregister/tombstone confirmation. Successful unregister now immediately refetches. `servers.test.tsx`, `environment.test.tsx`, `enrollment.test.tsx`; browser empty list. | Awaiting token feed failure currently becomes an empty list in `useFleet`; stale metrics rely on host status labels. No real host mutation performed. |
| `/servers/:hostId` Overview | PARTIAL | Host identity/runtime/metrics, environment change, typed revoke, credential rotation and re-enrollment dialogs tested in `views`, `lifecycle`, `reenroll`, `environment` tests. Docker authorization checkbox and snapshot scoping in `docker.host.test.tsx`. | Operational confirmation is UI/API-test evidence only. Event failure message does not clear on later recovery; no live credential rotation/re-enrollment. |
| `/servers/:hostId?tab=Monitoring` | PARTIAL | Metrics history, missing/stale data behavior through `HostDetail`, tab routing in console tests. | Real long-lived telemetry/service not available; no browser chart/history journey with a real host. |
| `/servers/:hostId?tab=Deployments` | PARTIAL | Scoped application list, ADMIN actions, explicit Docker authorization; corrected host deployments link now uses canonical route and retains tab. | No real Docker operations; start/stop are queued requests, not proof of container change. |
| `/servers/:hostId?tab=Activity` | WORKING (UI/API) | Host filter passed to operation history; paging/status filtering/error retry. | No live host history; filter paging inherits offset consistency under concurrent insertions. |
| `/hosts/:hostId` legacy | PARTIAL | Redirects to canonical server detail; console test coverage. | Legacy redirect does not preserve arbitrary query parameters. Current Docker link no longer depends on it. |
| `/servers/new` Automatic Setup | PARTIAL; real acceptance FAILED | Target discovery, explicit approval, durable confirmation reference/recovery, missing reference and no-target states; corrected JSON preflight header. Step/reason/uncertain warning and numeric diagnostic display covered in `automatic-setup.test.tsx` and `api/provisioning.test.ts`. Browser no-target/method switch. | Not a successful Ubuntu installation. Job recovery is sessionStorage-based; no global job listing/history or paste-existing-ID control. This prevents reliable cross-browser discovery of the historical job. No retry/admission/installer run here. |
| `/servers/new` Manual Bootstrap | PARTIAL | Host check, mode selection, token issue/error handling, CA path, command copy, token-linked enrollment proof tested in `onboarding`, `onboarding-proof`, `tls-trust`, `verified-install` tests. | No installer execution. Poll transport errors are currently ignored and can leave old verification state visible. Tokens only in memory, not URLs/localStorage. |
| `/applications`, `/deployments` | PARTIAL | Templates/apps/hosts reads, deploy queued/running/success/failure UI, start/stop error handling, VIEWER action exclusion, refresh in `applications.test.tsx`; browser empty state. API deployment tests pass. | No actual container execution. Deploy request then operation lookup can report a generic request failure after admission if lookup fails; polling errors are silent. Template fixed to `nginx-demo`; not a general deployment platform. |
| `/activity` | WORKING (UI/API/Browser) | Status filters, newest-first bounded paging, retry, empty/error states. Late obsolete-filter responses now ignored. `activity.history`, `activity.paging`, `activity` tests; browser empty history. | Operation history is not provisioning job history or global audit log. No explicit refresh button/automatic poll while staying on page. |
| `/settings` | WORKING (UI/API/Browser) | Account, sign-out error feedback, readiness/health recheck and degraded recovery guidance, copyable deployment references. Partial probe failures no longer show ready; stale probes cleared. `settings.test.tsx`; browser recheck. | Configuration is documentation only, not editable settings; no service restart offered. |
| Simulated resources | WORKING rejection (UI/API) | `client.guard.test.ts` and backend guards reject sim IDs; real views do not merge a browser-local simulated registry. | No active simulation-management route; do not advertise simulated hosts as real infrastructure. Test/browser fixtures are not real hosts. |
| Unknown paths | WORKING by inspection/UI routing | Fallback redirects to Overview; protected routes require session. | No dedicated 404 screen. |

## Confirmed defects repaired

1. **High — JSON preflight contract:** browser string body lacked JSON content type.
   Added header and direct client regression, not just a mocked provisioning method.
2. **High — false readiness:** one successful health probe could mask readiness
   failure, including stale green data after recheck. Clear failed feeds, surface
   partial probe failure, require both current probes before green readiness.
3. **High — stale fleet all-clear:** failed host refresh retained operational green
   banner. Suppress all-clear while refreshing or after host read failure.
4. **Medium — stale activity filter race:** old request could overwrite selected
   status results. Version requests and invalidate on cleanup. Independent review
   caught a pagination busy-state regression; a failing deferred-request test
   reproduced it and first-page replacement now resets pagination busy state.
5. **Medium — unregister feedback:** successful API revoke closed without refetch.
   Refresh only after confirmed success; existing tombstone/history semantics stay.
6. **Medium — Settings logout rejection:** rejected logout promise had no local
   feedback. Catch and report; do not pretend session closure.
7. **Medium — host deployments link:** legacy route dropped tab query through
   redirect. Link directly to `/servers/<id>?tab=Deployments`.
8. **Medium — inadequate setup diagnosis:** show persisted step/reason and unknown
   status before first poll; safe transport-status exception/event/API allowlist.
   Only numeric status is exposed, never stdout/stderr, token or arbitrary JSON.

Each repaired behavior was covered by an observed failing regression before its
fix. Extra timeout/spawn-error regressions confirm status remains unknown rather
than fabricating an exit code.

## Failed acceptance remains failed

Historical job `007ab9c1-9a05-4a43-9097-474b864e4d4b` remains, per preserved evidence,
`VERIFYING / INSTALL_ADMITTED / RECONCILIATION_REQUIRED`. Its token expired
unconsumed; no enrolled host/telemetry/service was observed. This session did not
query or mutate the acceptance runtime. A fixture reproduces the job response to
prove UI uncertainty, no success text, and no retry/add-another action.

Numeric exit status is the SSH transport/remote-command status, **not** an
authenticated installer-stage receipt. Status 255 and local signals are ambiguous;
nonzero remote status does not prove rollback. Timeout/spawn errors remain unknown.
No historical diagnostic can be reconstructed. `reconciliation_required`, ownership,
single-dispatch and retry policies are unchanged. No schema migration is needed.

## Checks actually run

| Check | Result |
|---|---|
| Baseline `cd frontend; npm test` | 162 passed |
| Final `cd frontend; npm test` | 174 passed, 27 files; React Router future warnings |
| `cd frontend; npm run build` | PASS: TypeScript and Vite, 69 modules |
| Backend baseline `python -m pytest backend/tests -q` | 379 passed, 10 skipped |
| Final `python -m pytest -q` | 532 passed, 11 skipped, 3 dependency deprecation warnings |
| Chromium `scripts/audit-browser.py` via webapp-testing `with_server.py`, port 15173 | PASS: primary routes/login/logout/empty states/recheck/setup methods; fixture API only; dev server stopped |
| Black check on 5 changed Python files | PASS |
| Ruff on 5 changed Python files, `--ignore B008` | PASS; unfiltered check reports 11 existing FastAPI Depends-default B008 findings |
| Strict mypy on 3 changed production Python modules | NOT CLEAN: existing `worker.py` claim CAS `Result[Any].rowcount` typing error; no success claim |

## Remaining blockers and next steps

1. Before claiming DEMO READY, run an isolated browser-to-real-API session with
   scratch operator accounts and no authorized provisioning targets; validate
   cookie/CSRF integration, role switching, network loss and recovery together.
2. Repair remaining known partial-state gaps above with focused regressions:
   token-feed availability, host-event recovery, manual proof staleness, admitted
   deployment lookup failure. Add a read-only global provisioning job list/detail
   flow with ownership enforcement; never hardcode the old job as succeeded/failed
   or rewrite its DB state to make the UI look terminal.
3. Add browser coverage with isolated host fixtures for every detail tab/dialog,
   keyboard behavior, responsive navigation and clipboard failure. Current browser
   smoke deliberately proves only a safe subset, not every control.
4. Fix the existing mypy rowcount issue separately and configure framework-aware
   Ruff handling rather than describing an ignored-rule run as globally clean.
5. Real Docker/service/Ubuntu workflows and new Automatic Setup acceptance require
   separately scoped authorization. Keep old evidence and spent state intact.

## Independent review and decisions

A fresh read-only reviewer inspected the changed code. Its medium pagination
finding was reproduced RED, repaired and verified with the full suites above.
Additional diagnostic allowlist rejection, failed unregister and symmetric health
failure tests were added and pass. Deferred minor: degraded health plus unavailable
readiness still says the readiness probe reports ready inside the degraded panel;
the separate warning correctly says readiness is unverified and no green banner
appears. This contradictory sentence should be corrected in the next focused pass.

Ruling: use fixture browser transport and disposable local API/HTTP tests, not the
acceptance runtime, to honor preservation/no-execution boundaries. Cost: a complete
browser-to-live-backend demo remains unverified. Ruling: preserve existing FastAPI
Depends conventions and CAS typing in this repair rather than broad lint/type
refactoring. Cost: unfiltered Ruff and strict mypy are not clean. The requested
exhaustive audit/repair is not complete; the matrix explicitly records the remaining
functional limitations rather than presenting rendering or mocked tests as proof.

No push, merge, production deployment, temporary sudo grant, live provisioning job,
installer, acceptance worker or infrastructure operation was performed.
