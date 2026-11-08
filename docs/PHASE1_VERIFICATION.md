# Phase 1 Verification Record — Single-Host Monitoring

Date: 2026-11-08. Branch: `feat/single-host-monitoring`.
Environment: Windows 11 development workstation (Python 3.13.7, Node 24.15.0).

Verdict summary: **PARTIAL** — all implementation acceptance criteria pass
with local evidence; **real Ubuntu VM verification is BLOCKED** (no
isolated Ubuntu VM/WSL available on this machine, and production DavidLab
is explicitly out of authorized scope). Everything below distinguishes
implemented / tested / verified live.

## A. Automated tests (executed, passing)

Command (repo root): `.venv\Scripts\python -m pytest -q`
Result: **45 passed** in ~7 s.

- Backend unit/API suite — 20 passed (`backend/tests`)
  - health endpoint; enrollment success; wrong enrollment token → 401;
    no configured token → 503; duplicate hostname rotates token and old
    token stops working; heartbeat/telemetry require auth (401);
    forged token → 401; other-host's token → 401; unknown host → 404;
    telemetry bounds validation (cpu>100 → 422; used>total → 422);
    persistence + latest-metrics reflection; missing telemetry → null
    (not zero); history ordering/newest-first + limit; ONLINE/STALE/OFFLINE
    unit tests on `compute_status`; no token material in public responses.
- Agent suite — 23 passed (`agent/tests`)
  - config validation (URL scheme, missing token, interval bounds);
    identity persistence/roundtrip/corrupt-file handling; REAL psutil
    collection asserted against `psutil.virtual_memory()`/`disk_usage`
    actual values and UTC timestamp freshness; retry/backoff behavior
    (success after transient failures, bounded retries, exponential
    backoff with cap, 401/403 never retried, retryable 5xx, 4xx not
    retried); main-loop enrollment flow, credential-rejection exit code 3,
    graceful stop with a real telemetry POST observed.
- Integration suite — 2 passed (`backend/tests_integration`)
  - real agent code → REAL uvicorn server on 127.0.0.1:8991 (thread) →
    SQLite; persistence asserted by direct DB query (not API echo);
    public API reflects honest ONLINE status; forged credential raises
    AuthError on the agent side; tampered payload (cpu 150%) → 422.

## B. Frontend tests and build (executed, passing)

Command: `npm test` (in `frontend/`) → **19 passed** (2 files).
Command: `npm run build` → `tsc -b && vite build`, 42 modules, built in
~2 s, output `dist/` (index 0.53 kB, CSS 13.44 kB, JS 180.92 kB).

Covered: loading/empty/error panels; counts; real metric values rendered;
missing telemetry → "—" + "No telemetry received" (never zeros); STALE and
OFFLINE hosts carry explicit warnings and are never counted online; host
detail identity/OS/agent-version rendering; "never" connectivity display;
404 handling.

## C. Live verification (executed on this workstation — NOT Ubuntu)

Sequence actually executed (recorded from shell history):

1. Backend started: `uvicorn app.main:app` on 127.0.0.1:8010
   (`NIMBUSOPS_ENROLLMENT_TOKEN=live-check-token-3f9a`).
2. Real agent process started with `NIMBUSOPS_AGENT_INTERVAL=10`,
   pointed at :8010. Enrollment succeeded (log: "enrolled new host
   hostname=DESKTOP-36UEJS7"); identity stored under `%TEMP%\nops-live`.
3. `GET /api/v1/hosts` → 200: host ONLINE, cpu 2.0%, ram 48.9% of
   23.7 GiB, disk 83.5% of 411.5 GiB (matches the machine's actual load).
4. Agent process killed → status remained ONLINE briefly (within
   threshold), then `STALE` verified after >90 s at default thresholds.
5. Second server (short thresholds: stale 30 s / offline 60 s) verified
   the full ONLINE → STALE (after 40 s) → OFFLINE (after 65 s)
   progression live, with telemetry rows retained and visibly historical.
6. Security boundaries against the live server:
   wrong enrollment token → 401 UNAUTHORIZED; forged agent token → 401;
   missing bearer token → 401; unknown host id → 404 HOST_NOT_FOUND.
7. Dashboard check: `vite` dev server (port 5174; 5173 occupied by an
   unrelated local app), proxy target set to the backend. Browser-path
   fetch through the dashboard (`localhost:5174/api/v1/hosts`) → 200 with
   the agent's live telemetry (cpu 9.7%, ram 50.2%, disk 83.5%).

## D. Not verified (blocked)

- **Ubuntu VM execution** of the agent: no WSL/VM available on this
  machine. The agent targets Linux (systemd example provided, paths use
  `/`), and psutil 7.0.0 supports Ubuntu; but per the roadmap's evidence
  rules this remains **planned for the isolated-VM gate**, not verified.
- OS-comparison tolerance check against `free`/`top` on Ubuntu (Phase 1
  roadmap criterion) — requires the VM.
- HTTPS/tunnel transport — no cross-network deployment in this phase.

## E. Manual regression notes

- Port 8000 was occupied by an unrelated local process on this machine;
  backend was run on 8010/8011/8020 via `--port`. `vite` auto-escalated
  5173→5174; the proxy target is configurable via `API_PROXY_TARGET`.
