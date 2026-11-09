# Stage B Verification Report — Real Docker Validation on david-lab

Branch: `feat/real-docker-validation` (commits `7a1fd95`, `30b3b80`).
Date: 2026-11-09. Topology: control server + dashboard on the Windows
development machine (Tailscale IP `100.70.17.124`), agent + Docker Engine on
`david-lab` (Tailscale `100.113.157.0`, Debian 13, Docker 29.9.2, 15
pre-existing production containers incl. SPECTRA on host port 8080).
**Everything below was executed against real infrastructure; no Docker
behavior was mocked.**

## 0. Environment decision (Stage A summary)

- Option A (dedicated KVM VM) rejected: `/dev/kvm` present but no
  virsh/qemu CLI installed (installing = mutation) and 3.1 GiB RAM headroom.
- Option B adopted: shared Docker daemon, isolated by name prefix
  (`nimbusops-`), dedicated port, user-scoped agent venv, no system changes.
- Template host port moved 8080 → **18080** (8080 is SPECTRA's).

## 1. Code fixes required by real infrastructure (merged in this branch)

1. `7a1fd95` — port 18080: backend seed (`services/deployments.py`), agent
   fallback (`docker_exec.py`), tests pinned to 18080.
   Also: root `.gitignore` `lib/` pattern was swallowing
   `frontend/src/lib/format.ts` (untracked since Phase 1; fresh clones could
   not build). Pattern anchored to `/lib/`, file committed.
2. `30b3b80` — **real bug found live**: `poll_commands` attached the
   template payload only to DEPLOY commands. Real STOP failed with
   `UNAPPROVED_OPERATION: container name '' outside managed prefix`
   because the agent had no `container_name`. Mocked tests fabricated the
   template, so 93 green tests never caught it. Fixed: template attaches to
   every op type; regression test
   `test_lifecycle_commands_carry_template_payload` (RED→GREEN).

## 2. Evidence timeline (all times UTC, 2026-11-09)

| Step | Command (abridged) | Result |
| --- | --- | --- |
| Enrollment | agent `--once` against `http://100.70.17.124:8000` | 200; identity `~/.nimbusops/agent.json` (0600) |
| Telemetry | `GET /api/v1/hosts` | david-lab ONLINE, cpu 26.6%, mem 58.2%, disk 12.7% (real psutil) |
| Deploy | `POST /applications/deploy` | 202 QUEUED op `40c4388c…`, container `nimbusops-nginx-demo-cab2f640` |
| Agent claim | poll ≤ 30 s | QUEUED→RUNNING→**SUCCEEDED** with evidence |
| Container truth | `docker inspect` | image `nginx:1.27-alpine`, labels `nimbusops.managed=true` + `nimbusops.deployment=269e4171…`, `privileged=false`, `Binds=null`, `restart=no`, `0.0.0.0:18080->80` |
| HTTP (local) | `curl 127.0.0.1:18080` on david-lab | **200** |
| HTTP (cross-net) | Windows → `http://100.113.157.0:18080/` | **200**, `Server: nginx/1.27.5` |
| STOP v1 (bug) | `POST …/stop` | FAILED `UNAPPROVED_OPERATION` (finding, fixed in `30b3b80`) |
| STOP v2 (fixed) | `POST …/stop` | 202 → **SUCCEEDED**, `container_state=EXITED`, curl → connection refused (exit 7) |
| START | `POST …/start` | 202 → **SUCCEEDED**, RUNNING, `http_ok=true`, curl 200 ×2 |
| Dedup | two STOPs while first in flight | same `operation_id`, second `deduplicated=true` |
| Offline queue | agent confirmed down (`pgrep`=0), queue STOP | stays **QUEUED** (25 s) |
| Reconnect | agent restarted | claims op → **SUCCEEDED**, `EXITED` (real evidence) |
| Restart app | `POST …/start` | **SUCCEEDED**, RUNNING, `http_ok=true` |

## 3. SPECTRA protection (before/after diff)

`docker ps -a` + `docker inspect` snapshots before and after the whole
exercise (`~/nimbusops-validation/spectra-*.txt` on david-lab):

- Only addition across the entire run: the single `nimbusops-nginx-demo-`
  entry (removed during cleanup).
- `spectra-frontend` `StartedAt=2026-11-08T07:23:08.554956095Z`,
  `spectra-backend` `StartedAt=2026-10-25T10:25:02.444944474Z` — **identical
  before and after**; no restarts, no policy changes, networks unchanged
  (`diff networks-before networks-after` → empty).
- Cleanup: agent stopped, container `docker stop` + `docker rm` by exact
  name; `docker ps -a --filter name=nimbusops- -q | wc -l` → **0**. No
  prune, no volume/image deletion, no daemon/firewall/daemon-config changes.

## 4. Real Docker verification — previously BLOCKED, now PASSED

The checklist from `docs/PHASE2_VERIFICATION.md` §8 ran for real:

| Check | Expected | Observed |
| --- | --- | --- |
| `docker ps --filter label=nimbusops.managed=true` | Up | Up (0.0.0.0:18080→80) |
| `curl http://…:18080/` after deploy | 200 | 200 (local + cross-network) |
| Stop via API, curl again | refused | refused (exit 7) |
| `docker ps -a --filter label=…` | Exited | Exited (0) |
| Start via API, curl | 200 | 200 |
| Unrelated containers before/after diff | identical | identical (uptime counters only) |

## 5. Test suites after the changes

| Suite | Command | Result |
| --- | --- | --- |
| Full Python (Phase 1+2+Stage B) | `python -m pytest -q` | **96 passed** |
| Frontend | `npm run test` | **18 passed** |
| Frontend build | `npm run build` | clean (43→ clean tsc+vite) |

## 6. Remaining known limitations (unchanged from Phase 2, re-rated by live evidence)

1. Stuck-RUNNING recovery: confirmed honest-by-design; offline queueing +
   reconnect claim verified live. Claim-timeout reconciliation stays Phase 3.
2. Dedup check-then-insert gap: not exercised live (single operator);
   backend first-write-wins held for the in-flight dedup case.
3. `app_url` is `http://localhost:18080/` — cosmetic only for remote
   operators (real URL `http://100.113.157.0:18080/`); deferred.
4. Result truncation (2048 chars): not reachable with nginx-demo payloads.
5. Unauthenticated mutation endpoints: trusted-local model, tailnet-private
   test; RBAC stays Phase 5.

## 7. Environment state left behind (for Stage C / re-runs)

- david-lab: `~/projects/nimbusops/NimbusOPS` clone at `30b3b80` with
  `.venv`; agent identity `~/.nimbusops/agent.json`; snapshots in
  `~/nimbusops-validation/`; agent process stopped.
- Windows: backend SQLite (`backend/nimbusops.db`) retains the full
  operation history incl. the FAILED-then-fixed STOP — kept as evidence.
- SPECTRA and all 14 other containers: untouched, verified byte-identical.
