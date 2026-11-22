# Full MVP candidate — operator runbook

## Scope and release gate

This is an undeployed development candidate. Do not use the older quick-start as
authorization for production or privileged installation. The final gate lives in
`FULL_MVP_RC_STATUS.md`; real Ubuntu Zero-Touch and Docker acceptance are mandatory.
The approved dashboard design is unchanged.

## Local disposable demonstration (Windows)

Prerequisites must already exist: Python 3.11+ with backend requirements, Node20+
and frontend dependencies. No installer/package manager is needed for demonstration.

In a fresh PowerShell terminal, from this integration repository:

```powershell
$Repo = (Get-Location).Path
$Python = (Get-Command python -ErrorAction Stop).Source
$Demo = Join-Path $env:LOCALAPPDATA ('Temp\opencode\nimbusops-fullmvp-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Demo -ErrorAction Stop | Out-Null
Get-ChildItem Env: | Where-Object Name -Like 'NIMBUSOPS_*' |
    ForEach-Object { Remove-Item "Env:$($_.Name)" }
$env:PYTHONPATH = $Repo
$env:NIMBUSOPS_DATABASE_URL = 'sqlite:///' + (Join-Path $Demo 'demo.sqlite3').Replace('\', '/')
$env:NIMBUSOPS_TOKEN_PEPPER = [guid]::NewGuid().ToString('N')
$env:NIMBUSOPS_ENROLLMENT_MODE = 'disabled'
$env:NIMBUSOPS_SESSION_COOKIE_SECURE = 'false' # LOCAL HTTP ONLY
$env:NIMBUSOPS_BROWSER_ORIGINS = 'http://127.0.0.1:5173'
$env:NIMBUSOPS_CORS_ORIGINS = 'http://127.0.0.1:5173'
Set-Location $Demo # empty CWD prevents loading repository .env
& $Python -c "import os, pathlib, runpy; runpy.run_path(str(pathlib.Path(os.environ['PYTHONPATH']) / 'frontend/scripts/finalization-browser.py'))['seed']()"
if ($LASTEXITCODE -ne 0) { throw 'Seed failed; do not start backend' }
& $Python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Second terminal: set `$Repo` to the same integration path, then:

```powershell
Set-Location (Join-Path $Repo 'frontend')
$env:API_PROXY_TARGET = 'http://127.0.0.1:8000'
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Dashboard: `http://127.0.0.1:5173`; health:
`http://127.0.0.1:8000/api/v1/health`. Use `browser-viewer` for read-only exploration
or `browser-admin` for owner-scoped history; fixture password is
`Disposable-browser-only-42!`. These credentials are public synthetic fixtures,
never staging credentials. No SSH worker/agent is required. Telemetry ages naturally.

Stop both terminals with Ctrl+C, then close them to discard local environment.
Do not kill all Python/Node processes. Demo state is retained at the printed/chosen
temporary folder; never delete a database by an ambiguous/default path.

## Candidate installation/configuration (not executed)

1. Freeze exact code SHA and run complete regression/build/security gates.
2. Use a new dedicated Ubuntu24.04 amd64 acceptance guest and new machine binding,
   SSH identity/known-host file, hostname, database and operator identity.
3. Establish verified HTTPS (public CA or explicit protected private CA). Never use
   curl `-k`, disabled HTTPX verification, permissive SSH host-key handling, or broad sudo.
4. Persist the database, token pepper, operator credentials, target-policy files,
   agent identity and pending outcome journal outside release directories. Protect
   backups as secrets. Never publish demo credentials or private key material.
5. Backend binds loopback; reverse proxy serves `/api` and immutable `/releases` as
   well as frontend. Configure exact browser origins, secure session cookies and
   proxy management restrictions. Validate proxy config before enabling it.
6. Automatic Setup is an opt-in separate worker using the approved target policy.
   No automatic worker startup is authorized here. A pinned artifact and successful
   transport exit do not prove enrollment or readiness.
7. The canonical installer creates an unprivileged **telemetry-only** service.
   Docker operations require a separately reviewed, explicitly enabled executor
   identity/profile; never silently add that service account to the Docker group.

## Recovery rules

- Provisioning admission is durable before any remote side effect. After timeout,
  disconnect, cancellation or worker crash: inspect safe events and reconcile the
  consumed bootstrap identity plus fresh heartbeat/telemetry. Never redispatch an
  admitted uncertain job merely because the installer is not visible.
- Numeric installer exit and transport exit are distinct evidence, not proof of
  rollback. Do not copy raw privileged logs into UI/API responses.
- Agent pending results are atomically persisted beside its identity. Restart
  resubmits pending outcomes using the current claim generation instead of rerunning
  Docker. There remains a crash window between Docker effects and journal write;
  this is not exactly-once execution.
- A damaged/unreadable pending journal is a fail-closed startup error. Preserve it;
  inspect owned containers and backend operation states with authorization. Do not
  delete the journal to force execution. Restore/reconcile only after matching the
  agent identity and operation IDs and resolving uncertain side effects.
- Connectivity after browser refresh is not proof of successful operations. UNKNOWN
  remains uncertain until backend/operator reconciliation establishes an outcome.

## Backup/restore and rollback

Use SQLite's online backup API (or stop all writers before a filesystem copy), not
an arbitrary copy of a live WAL database. Include protected configuration and token
pepper in a separately protected backup; preserve agent identities/journals. Restore
to a **new disposable path** first, verify integrity/foreign keys and migration
idempotence, and check authentication and representative telemetry. Local regression
coverage is in `backend/tests/test_full_mvp_monitoring.py`.

Rollback code and schema compatibility must be reviewed together. Never roll back
an acceptance snapshot or replace its database to erase a failed attempt. Never
restore old agent credentials while their identity remains live without explicit
reconciliation. Stop only owned processes; keep safe logs and operation IDs.

## Consolidated fresh acceptance authorization

Authorize one new disposable Ubuntu24.04 amd64 guest (or two if separating Docker
executor privileges), independent of all historical infrastructure, with explicit:

- Machine/hostname/IP/SSH host-key identity, permitted network endpoints and budget.
- Package installation (`python3`, `python3-venv`, CA certificates and, if absent,
  Docker Engine), protected CA copy if needed, dedicated users/state/systemd units.
- Narrow reviewed root launcher/sudo policy for one fresh Zero-Touch action; new
  job/token/state/approval only. Remove the grant and verify denial afterward.
- Dedicated Docker executor permission, approved pinned template/image, loopback
  published port, CPU/memory/PID limits, and only uniquely labeled test containers.
- Controlled backend/agent restart and bounded network interruption, plus cleanup
  of only newly owned containers/services/grants with retained evidence.

No DavidLab, Azure, production, historical acceptance guest/database, old launcher,
spent marker, snapshot or approval is included. Authorization must name the frozen
candidate SHA and permitted actions before any such execution.
