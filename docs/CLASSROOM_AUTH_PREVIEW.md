# Isolated classroom authentication preview

## Boundary and compatibility

Feature branch: `feature/classroom-auth`. The original `demo/multihost-rc2`
worktree and its running API/UI/agent are not changed. Never run this branch
against the live database without separately approved integration.

Human authentication extends `operators` and `operator_sessions`; no schema
migration is added. Existing PBKDF2 hashes remain accepted without rewriting
ADMIN credentials; new accounts use argon2-cffi's Argon2id. Agent enrollment,
heartbeat/inventory, telemetry, polling, and result protocols are unchanged.
Operational reads now require human authentication. Existing ADMIN write
dependencies remain enforced. Old anonymous monitoring clients must log in.

Browser sessions use HttpOnly, SameSite=Strict, host-only cookies scoped to
`/api/v1`, with database-backed expiration and logout revocation. Cookie
mutations require a session-bound HMAC CSRF token and reject foreign origins.
The browser never receives a bearer session credential. Legacy bearer operator
APIs remain available for existing non-browser clients. Health/readiness and
schema documentation remain public, not host data.

## Start the already prepared preview

From this feature worktree, in two separate ordinary PowerShell terminals:

```powershell
$env:NIMBUSOPS_AUTH_PREVIEW_HOME = '<absolute path to an empty private preview home>'
.\.venv\Scripts\python -m backend.scripts.start_auth_preview api
```

```powershell
$env:NIMBUSOPS_AUTH_PREVIEW_HOME = '<absolute path to an empty private preview home>'
.\.venv\Scripts\python -m backend.scripts.start_auth_preview ui
```

Do not start duplicates while ports are occupied. The launcher defaults to UI
`http://127.0.0.1:18421` and API `http://127.0.0.1:18420`; override with
`NIMBUSOPS_PREVIEW_UI_PORT` / `NIMBUSOPS_PREVIEW_API_PORT` and set
`NIMBUSOPS_PREVIEW_UI_BASE_URL` for the smoke harness. Private environment,
logs, database, process IDs, and browser result are under the preview home.
Do not publish that directory.
The preview has no copied host credentials and no connected physical hosts.
An empty fleet is intentional, not failed monitoring.

The existing ADMIN was copied to this private database with the same ID,
username, hash and role. Its live row was read only, not changed. Exactly one
`viewer` account was provisioned with the user-specified classroom password;
no password appears in source or this guide. Existing private ADMIN credential
delivery remains unchanged. The preview's viewer credential record is private.

## Explicit setup for a fresh private environment

Set an absolute `NIMBUSOPS_DATABASE_URL` to a NEW private database, a private
random `NIMBUSOPS_TOKEN_PEPPER`, `NIMBUSOPS_ENROLLMENT_MODE=disabled`, and
`NIMBUSOPS_BROWSER_ORIGINS=http://127.0.0.1:18421` before importing the app.
Initialize tables using `create_all()` and `upgrade_phase3b()`. Create the first
ADMIN with hidden password prompts:

```powershell
.\.venv\Scripts\python -m backend.scripts.create_operator --username presenter-local
.\.venv\Scripts\python -m backend.scripts.create_classroom_viewer --classroom-only
```

The second command accepts the classroom password through hidden input and
refuses an existing `viewer`; it never resets an existing account. Normal
ADMIN setup retains the 12-character minimum. The classroom exception accepts
8–128 characters only in explicit local setup. No account-management API exists.

Secure cookies default ON. The HTTP loopback preview explicitly sets
`NIMBUSOPS_SESSION_COOKIE_SECURE=false`; HTTPS environments must leave it true.
Use the exact preview origin, not a different hostname. A separate browser
profile is recommended: cookies are scoped by hostname/path, not TCP port.
Do not open the old and new dashboards in the same browser context during demo.

## Two-minute classroom demonstration

1. 0:00–0:25: Open `/servers` in a private browser context; show the login gate.
2. 0:25–0:55: Log in as viewer privately. Show Overview, Servers, Activity and
   disabled deployment controls. Explain empty fleet is isolated on purpose.
3. 0:55–1:15: Refresh; show the same VIEWER identity remains signed in.
4. 1:15–1:40: Log out, sign in as the existing ADMIN privately; show Add Server
   is available. Do not issue tokens, unregister hosts, authorize Docker or deploy.
5. 1:40–2:00: Log out. Explain backend role checks, CSRF and independent agents.

## Rollback / integration gate

No live cutover occurred, so no live database rollback is required. Stop only
the preview processes after checking their recorded IDs AND command identities,
or Ctrl+C the two foreground terminals. Never kill by port alone. Keep the
private database for recovery; do not delete live identities or runtime state.
Integration requires separate approval, an online SQLite backup, preserved
pepper, origin/cookie configuration review and regression acceptance. Do not
merge, repoint Vite, restart the live API or migrate the demo automatically.

## Limitations

- Classroom password is deliberately weak; loopback-only, not production use.
- Login limiter is bounded in-memory per username, one worker; restart clears
  it. No shared/distributed limiter, MFA, account disabling or password-reset UI.
- No idle timeout beyond the existing absolute session expiry.
- No live physical-agent attachment or Docker operations in this preview.
- Legacy bearer login remains for compatibility; do not store its response in
  browser storage. TLS is required beyond this loopback-only demonstration.
- Dependency deprecation warnings remain; no complete dependency audit claimed.
- Deferred review minors: classroom setup trusts the selected database rather
  than enforcing a preview-only path; UI launcher validates the database but
  trusts `API_PROXY_TARGET`. Before using either with a fresh configuration,
  explicitly verify the NEW private database path and exact API target
  `http://127.0.0.1:18420`. Do not use inherited/live environment settings.
