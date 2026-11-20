# Optional local end-to-end check (not a CI gate)

`frontend/scripts/e2e-onboarding.mjs` drives a real browser against a real
control plane. It is committed so the acceptance path is reproducible, but it
is **not** part of CI and it is **not** run by `npm test`.

## Why it is optional

- It needs Playwright and Chromium, which the project does not install by
  default (`frontend/package.json` has no Playwright dependency yet).
- It mutates state: the enrollment wizard issues a real single-use bootstrap
  token, which expires on its own TTL but is visible to the control plane.
- It needs a seeded ADMIN and VIEWER operator, so it must run against a scratch
  database — never the live fleet database.

## Run it

```bash
cd frontend
npm i -D playwright
npx playwright install chromium
npm run e2e:onboarding
```

Start the API and Vite dev server first (see `docs/DEVELOPMENT.md`), then pass
credentials through the environment:

```powershell
$env:NIMBOPS_E2E_BASE_URL       = "http://127.0.0.1:5173"
$env:NIMBOPS_E2E_ADMIN_USER     = "e2e-admin"
$env:NIMBOPS_E2E_ADMIN_PASSWORD = "<scratch password>"
$env:NIMBOPS_E2E_VIEWER_USER    = "e2e-viewer"
$env:NIMBOPS_E2E_VIEWER_PASSWORD= "<scratch password>"
# optional: a host whose credential is revoked in the scratch DB
$env:NIMBOPS_E2E_REVOKED_HOST_ID = "<host id>"
npm run e2e:onboarding
```

Passwords stay in the environment; nothing secret is written to argv or into
the page URL.

## What it asserts

1. ADMIN signs in through the cookie-only browser session.
2. The enrollment wizard issues a real, single-use bootstrap token from the
   control plane, shows it once, and never places it in the URL.
3. VIEWER has no Deploy/Start/Stop controls and no enrollment action.
4. When a revoked host id is supplied, that host is labelled `Revoked` and is
   never simultaneously rendered as `Offline`.

## Status

Written and committed in Sprint 1, **not yet executed here** because Playwright
is not installed in this workspace. Treat a passing run as local evidence only;
CI gating is a separate infrastructure decision.
