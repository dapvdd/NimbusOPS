# NimbusOps CI

`.github/workflows/ci.yml` defines the Phase 3A.5 quality gates. It runs the
existing test suites and production build on every pull request targeting
`main` and every push to `main`.

CI is deliberately independent of DavidLab, Docker Engine, external APIs, and
production infrastructure. It needs no secrets, SSH credentials, Tailscale
authentication, or deployment permissions.

## Triggers

| Event | Branches | Purpose |
|---|---|---|
| `pull_request` | `main` | Block merging a change that fails tests or build |
| `push` | `main` | Verify the merged result on `main` |

`pull_request` (not `pull_request_target`) is used so pull requests from forks
run with a read-only token and no secrets. A newer run on the same branch
cancels the previous one through the `concurrency` group.

## Jobs and expected checks

| Check name | What it proves | Commands |
|---|---|---|
| `Python tests` | Backend, agent, and loopback integration suites pass | `python -m pytest -q` |
| `Frontend unit tests` | Vitest suite passes | `npm ci` then `npm test` |
| `TypeScript and Vite build` | Types are valid and the production bundle builds | `npm ci`, `npx tsc -b`, `npx vite build` |

`python -m pytest -q` covers `backend/tests`, `agent/tests`, and
`backend/tests_integration` through `pytest.ini`. The integration tests start
loopback uvicorn servers and use a mocked Docker executor; they do not need
Docker Engine or a managed host.

## Runtime versions

| Tool | Version | Why |
|---|---|---|
| Python | `3.13.7` | Matches the verified local interpreter |
| Node.js | `24.15.0` | Matches the verified local runtime and `package-lock.json` |
| Runner | `ubuntu-24.04` | GitHub-hosted, pinned OS image; no self-hosted infrastructure |

Versions are pinned exactly so a passing local run and a CI run use the same
major, minor, and patch releases.

## Dependency caching

- **npm:** enabled through `actions/setup-node` with
  `cache-dependency-path: frontend/package-lock.json`. The lockfile is committed
  and `npm ci` fails if it disagrees with `package.json`.
- **pip:** intentionally not cached. `backend/requirements.txt` and
  `agent/requirements.txt` pin direct dependencies but there is no hash-locked
  Python lockfile, so caching is skipped rather than keyed on an incomplete
  manifest.

## Network dependencies

CI downloads pinned actions, the pinned Node/Python runtimes, and packages from
the public npm and PyPI registries. It never calls NimbusOps, DavidLab,
Tailscale, Docker Engine, or any production API at runtime.

## Permissions and supply chain

- Workflow-level `permissions: contents: read`; no job requests more.
- `persist-credentials: false` on checkout, so the workflow token is not left in
  the local Git configuration.
- Third-party actions are pinned to immutable commit SHAs:
  - `actions/checkout` `3d3c42e5aac5ba805825da76410c181273ba90b1` (v7.0.1)
  - `actions/setup-python` `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` (v7.1.0)
  - `actions/setup-node` `949feb2413d6458794dcd2491c4babbbce0c15c1` (v7.1.0)
- No secrets, environment variables, service containers, SSH, Tailscale, or
  deployment steps are configured.
- No `pull_request_target`, `workflow_run`, or `write` permission is used.

To update an action, resolve the new tag to a commit SHA and change both the
`uses:` value and its version comment in the same commit:

```bash
gh api repos/actions/checkout/git/ref/tags/v7.0.1 --jq .object.sha
```

## Reproducing locally

Linux/macOS:

```bash
python -m venv .venv
.venv/bin/pip install -r backend/requirements.txt -r agent/requirements.txt
.venv/bin/python -m pytest -q

cd frontend
npm ci
npm test
npx tsc -b
npx vite build
```

Windows PowerShell (verified environment):

```powershell
.\.venv\Scripts\python.exe -m pytest -q

cd frontend
npm.cmd ci
npm.cmd test
npx.cmd tsc -b
npx.cmd vite build
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `npm ci` fails with `EUSAGE` | `package-lock.json` out of sync with `package.json` | Run `npm install` locally, commit the updated lockfile |
| `npm ci` fails on optional native binary | Node version differs from the pinned one | Use Node `24.15.0` |
| Vitest exits non-zero with `act(...)` warnings only | Warnings are not failures | Check the summary; only failed assertions fail the job |
| Python tests fail to import `backend` or `nimbusops_agent` | `pytest.ini` not honoured or wrong working directory | Run `python -m pytest -q` from the repository root |
| Integration test cannot bind `127.0.0.1:8991` | Another process holds the port | Stop the local server; CI runners are isolated |
| `tsc -b` reports stale build info | Cached `.tsbuildinfo` | Delete `frontend/*.tsbuildinfo` and rerun |
| Workflow does not start | Branch or event does not match | It runs only for PRs to `main` and pushes to `main` |
| Cache hit uses old dependencies | Lockfile unchanged | Cache keys follow the lockfile; update it or clear the cache in Actions settings |

## Limitations

- The workflow is validated by YAML parsing and by running the same commands
  locally. GitHub's schema validation only happens when the workflow runs; there
  is no offline GitHub Actions schema validator in this repository.
- Python dependencies are pinned but not hash-locked, so transitive resolution is
  only as reproducible as PyPI allows.
- Integration tests are loopback HTTP with a mocked Docker executor. They do not
  prove behaviour on an Ubuntu host with a real Docker Engine or agent.
- There is no coverage threshold, frontend lint script, E2E browser run, or
  screenshot check.
- Branch protection is not configured by this change. Recommended: require the
  three checks above on `main` and disallow direct pushes.

## Recommended next steps

1. Push the branch and open a pull request; confirm all three checks appear and
   pass.
2. Enable branch protection on `main` requiring `Python tests`,
   `Frontend unit tests`, and `TypeScript and Vite build`.
3. Add a hash-locked Python dependency file (for example `pip-compile
   --generate-hashes`) before enabling pip caching.
4. Add frontend linting and coverage thresholds once those tools exist.
5. Keep CI free of deployment credentials; Phase 3B enrollment work must add its
   own isolated tests rather than reusing production secrets.
