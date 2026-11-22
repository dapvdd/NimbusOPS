# NimbusOps dashboard functional readiness — 2026-11-22

## Finalization verdict: DEMO READY — bounded local demonstration

The dashboard is ready for the verified local demonstration using synthetic data
and real React/FastAPI processes. This is **not** real infrastructure acceptance,
production/deployment approval, an exhaustive all-controls browser certification,
or a repository-wide typing-clean verdict. The finalization ledger is
`docs/superpowers/plans/2026-11-22-dashboard-finalization.md`. The finalization
matrix below supersedes the historical baseline at `ce177eb` retained afterward.
Automatic Setup remains **NOT ACCEPTED** for real provisioning; historical
acceptance evidence and runtime were not accessed or modified.

Coordinator verification during resumed sprint: full Python suite **542 passed,
11 skipped**, with three dependency deprecation warnings. Scoped Ruff and Black
passed for the history API, worker typing repair and history tests. Strict mypy
passes for the two changed production modules with `--follow-imports=silent`;
unrestricted import checking still finds 24 errors in six other modules. This is
not a repository-wide typing-clean claim.

### Finalization evidence matrix

| Surface | New evidence | Remaining boundary |
|---|---|---|
| Login/session/CSRF | Disposable real-browser runs: invalid/valid login, reload, HttpOnly/SameSite cookie, missing CSRF and untrusted Origin rejection, logout, VIEWER restrictions; expanded run also verifies server-revoked session redirects and reauthentication | Expiry uses revocation, not elapsed TTL |
| Overview and Servers | Real synthetic fleet search/environment/refresh; token feed failures are distinct from empty results; VIEWER token request role gate has focused regressions | No real managed fleet observed; token feed remains bounded to 50 |
| Host detail and tabs | Real backend fixture host across Overview/Monitoring/Deployments/Activity; dialog dismissal and focus restoration; host-event recovery regression | Destructive confirmations not submitted; real lifecycle/Docker actions not exercised |
| Automatic Setup history | Owner-scoped ADMIN GET list/detail, metadata allowlist, pagination/access tests; expanded real browser 50→65 jobs, refresh/inspection/status refresh/reference recovery; foreign-owner list exclusion and detail 404 | No admission/dispatch/installer; NOT ACCEPTED |
| Manual Bootstrap | Shared automatic/manual proof refresh invalidates stale success on failure; component regressions; browser hostname/mode controls | No browser token generation or installer; enrollment proof uses isolated tests |
| Applications | Admitted IDs retained through lookup errors, read-only recheck, UNKNOWN write lock; original 11 tests restored alongside remount/operator/host/storage-failure regressions | SessionStorage is same-tab only; no cross-tab guard or recovery of an interrupted POST without returned ID; no container execution |
| Activity | Real backend 50→65 paging, FAILED filter→22, empty RUNNING filter | Synthetic offline rows, not real infrastructure activity |
| Settings/clipboard | Actual Chromium clipboard, live health probes/recheck; corrected unverified-readiness wording and copy failure regressions | Configuration stays documentation-only; no restart or deployment |
| Responsive/error recovery | Chromium 390×844 viewport, no horizontal overflow; explicitly injected browser-offline mode and real Retry recovery | Not assistive-technology certification or every device/browser |

All live fixtures use a new disposable SQLite database and synthetic accounts,
hosts, operations and disabled provisioning metadata. No core API interception is
used. Offline mode is an explicitly injected transport fault, not a live outage.
The original historical job is not the seeded browser fixture and remains untouched.

Coordinator runs `python frontend/scripts/finalization-browser.py` against actual
local Vite/FastAPI processes. This does not prove actual backend-crash recovery,
elapsed session TTL, installer success or real infrastructure behavior. Latest
counts and artifact paths are recorded below. Final admission-review repairs passed
the subsequent combined frontend test and production build gates.

Independent review: owner/admin isolation, metadata/event allowlists, unresolved
confirmation preservation, failed manual-proof invalidation, read-only history and
typing-only worker CAS changes had no additional Important findings. An Important
enabled→busy dialog focus transition was repaired with four observed failing
regressions followed by 13 focused passes; coordinator combined frontend gate is
now **226 tests/32 files**, and fresh production build passes. Real Chromium
busy-transition verification also passes in the latest 19-check run below. Deferred minor: offset
pagination may repeat a history row if jobs are inserted between pages; no cursor
snapshot guarantee is claimed. Subsequent review covers the deployment/feed/browser
changes separately.

Deployment review identified additional Important cases: server-reported
UNKNOWN allowing lifecycle writes, deployment/lifecycle cross-panel guards, and a
delayed admission response arriving after navigation/remount. Eight new regressions
were observed failing before the fix and all 32 Applications tests now pass,
including the retained 11 original tests. Shared pending/admission subscriptions,
server UNKNOWN/cross-panel guards, fail-closed storage-read recovery and
ADMIN→VIEWER→ADMIN reference/polling isolation address those findings. Same-tab
pending markers block resubmission after reload before an ID arrives, but recovery
then requires backend/operator reconciliation; cross-tab coordination is not claimed.

### Sprint commits (local only)

- `e2f8809` — owner-scoped read-only provisioning history API, access/pagination/
  secret/read-only regressions and typed worker CAS result.
- `235c4b5` — token/event/manual/readiness/clipboard/dialog recovery and discoverable
  read-only setup history, with unresolved confirmation preservation.
- `0cd4f96` — disposable real-browser/backend integration and isolated busy-dialog
  focus coverage (19 checks).
- `84c8279` — admitted-operation persistence, delayed response recovery, UNKNOWN
  guards and review regressions.

Branch remains `dev/dashboard-functional-audit`; no push, merge or deployment.
Unrelated acceptance documents, wrapper tooling and existing evidence are excluded.

### Current finalization gates

| Command | Coordinator result |
|---|---|
| `python -m pytest -q` | 542 passed, 11 skipped, 3 dependency warnings |
| `cd frontend; npm test` | 226 passed, 32 files, after final review repair |
| `cd frontend; npm run build` | PASS, TypeScript + Vite, 70 modules |
| `cd frontend; npx tsc --noEmit` | PASS |
| `python -m ruff check backend/app/api/provisioning.py backend/app/provisioning/worker.py backend/tests/test_provisioning_history.py frontend/scripts/finalization-browser.py` | PASS, no ignored B008 |
| `python -m black --check` on those four Python files | PASS |
| `python -m mypy --strict --follow-imports=silent backend/app/api/provisioning.py backend/app/provisioning/worker.py` | PASS, 2 files |
| Same strict mypy without `--follow-imports=silent` | NOT CLEAN: 24 errors in 6 imported modules; no repository-wide typing claim |
| `git diff --check` | PASS, line-ending conversion warnings only |

No frontend ESLint/format script is configured in `frontend/package.json`; no
frontend lint-clean claim is made. TypeScript/build and tests are distinct gates.

Latest coordinator browser rerun: **19 passed, 0 failed**, artifacts at
`C:\Users\user\AppData\Local\Temp\opencode\nimbusops-real-browser-z65m58gt\`.
The additional **SAFE ISOLATED** check imports the actual Vite-served ConfirmDialog
and React into a dedicated page: submission changes local busy state only,
disabled-button focus is retained inside the modal, Tab/Shift+Tab remain contained,
busy Escape is ignored and closing restores the trigger. It performs zero API
requests and is not presented as an operational confirmation test. The 18 real
route/backend journeys also pass; owned processes/storage are cleaned up.

### Remaining boundaries and exact next action

- Admission recovery regressions use mocked requests, not live operational POSTs;
  no container, installer, SSH target or worker execution was authorized.
- Persistence is same-tab only. A full reload before the admission ID arrives
  leaves a fail-closed pending reference requiring reconciliation. Storage-write
  failure cannot guarantee recovery after a full reload; an explicit warning is shown.
- Deferred minors: concurrent insertions can duplicate offset-paged history rows;
  browser viewer assertion checks no matching 403s rather than all token requests
  (unit tests assert no request); harness mutation audit is not a comprehensive
  operational-endpoint allowlist. Inspected journeys avoid those writes.
- Browser faults cover explicit offline mode, not backend crash; session invalidation
  uses revocation, not elapsed TTL. Real assistive-technology audit is unperformed.
- Exact next safe action: run `python frontend/scripts/finalization-browser.py` for
  the bounded presentation. Real Automatic Setup acceptance needs a separate scope
  and authorization; do not retry/rearm the preserved historical job or reuse spent
  acceptance evidence/approval markers.

Execution ruling: resume existing delegated sessions rather than restart inline,
as explicitly requested after quota refresh. Cost: duplicated context overhead,
mitigated with exclusive ownership and coordinator combined gates. No new schema,
infrastructure, push, merge, deployment, sudo or historical-state mutation occurred.

## Baseline verdict: PARTIALLY READY

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
