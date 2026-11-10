# Phase 3B Architecture — Secure Real-Host Enrollment

**Status:** DESIGN — NOT IMPLEMENTED. Requires user approval before any Phase 3B code.
**Date:** 2026-11-10 · Branch: `feat/phase3b-secure-enrollment`
**Evidence base:** code audit at `main` @ `f9ae5de`; docs `SECURITY.md`, `ARCHITECTURE.md`, `PHASE3A_NOTES.md`, `PRD-v2.0.md`; local DB `backend/nimbusops.db` inspected read-only.

---

## 1. Current Architecture Findings (Audited)

### 1.1 Components and Trust Boundaries Today

```text
Browser (untrusted) --HTTP--> Control Server (FastAPI/SQLite) <--HTTP(poll)-- Agent (semi-trusted)
                                     |                                                |
                              SQLite via create_all()                    Docker CLI (constrained, argv-fixed)
```

**Server** (`backend/app/main.py`): three routers — `public.py` (hosts/health), `agents.py` (enroll/heartbeat/telemetry/commands), `applications.py` (templates/applications/deploy/start/stop). CORS allowlist, `*` rejected at startup; methods GET/POST only.

**Database**: SQLite, `create_all()` at startup (`core/db.py:43`) — no Alembic. FK pragma + busy_timeout 5000 per connection.

**Agent**: outbound-only HTTP, identity in `~/.nimbusops/agent.json` as plaintext JSON, chmod 0600 best-effort on POSIX, skipped silently on Windows (`config.py:69-75`).

**Frontend**: typed fetch wrapper (`client.ts`); simulated hosts in `localStorage` as `sim-<uuid>`.

### 1.2 Endpoint Inventory with Auth Status

| Method/Path | Auth | Mutates? | Evidence |
|---|---|---|---|
| GET `/api/v1/health`, `/hosts`, `/hosts/{id}`, `/hosts/{id}/metrics` | none | no | `public.py` |
| GET `/api/v1/templates`, `/applications`, `/applications/{id}/container-state`, `/operations/{id}` | none | no | `applications.py` |
| POST `/api/v1/applications/deploy`, `/{id}/start`, `/{id}/stop` | **none** | **yes** | `applications.py:65-80` |
| POST `/api/v1/agents/enroll` | enrollment token (body) | creates host | `agents.py:31-45` |
| POST `/api/v1/agents/heartbeat`, `/telemetry` | `X-Host-Id` + Bearer token | updates host | `agents.py:54-89` |
| POST `/api/v1/agents/commands/poll`, `/commands/{id}/result` | `X-Host-Id` + Bearer token | claims/updates op | `agents.py:95-123` |

### 1.3 Key Code Evidence

**Enrollment re-revokes by hostname** (`services/hosts.py:77-103`): `existing.is_revoked = False` on re-enrollment — revoking `david-lab` and re-enrolling it unauthenticated restores its credential.

**Enrollment dedup race** (`services/hosts.py:87-88`): check-then-insert is non-atomic; concurrent identical hostnames pass both checks and two records get created (SQLite WAL would expose this further).

**Agent identity in plaintext** (`agent/nimbusops_agent/config.py:69-75`): `agent_token` stored in `~/.nimbusops/agent.json` as readable JSON. Anyone who can read that file can impersonate the host.

**No operator auth on mutations** (`backend/app/api/applications.py:1-6`): comment explicitly says "Phase 2 trusted-local model" — no `Depends` guard on any application endpoint.

**Existing host in local DB** (inspected, read-only): `david-lab` (id: `5ca406e8…`) enrolled 2026-11-09, active, credential stored as SHA-256 hash; `local-probe` (inactive). Both with `is_revoked=0`.

---

## 2. Proposed Phase 3B Architecture

### 2.1 High-Level Trust Model

```text
Operator (browser, authenticated) --> Control Server (FastAPI/SQLite)
                                               |
                          +--------------------+--------------------+
                          |                                         |
                    Agent A (real)                         Agent B (real)
                   (own credential)                      (own credential)

  Simulated hosts (localStorage sim-<uuid>) NEVER reach the backend API.
```

**Browser → Server**: all state-changing endpoints require authenticated operator session (cookie or Bearer). Public GET endpoints (host list, telemetry, health) remain unauthenticated in Phase 3B (trusted-local model preserved until explicit operator auth is enabled).

**Agent → Server**: all endpoints require `X-Host-Id` + `Authorization: Bearer <agent-token>` as today. Bootstrap token only used at enrollment time.

### 2.2 Bootstrap Enrollment Flow

```
1. Operator authenticates to the dashboard.
2. Operator requests enrollment for a new host.
3. Server generates a BOOTSTRAP token:
   - 256-bit random, single-use, short-lived (default: 10 minutes).
   - Stored as SHA-256 hash in `bootstrap_tokens` table (id, hash, scope_hostname, created_by, created_at, expires_at, consumed_at, consumed_by_host_id).
   - Shown once to the operator in the UI; operator copies to the target host's shell/secure channel.
4. Agent starts with `--bootstrap-token <token>` (env: NIMBUSOPS_AGENT_BOOTSTRAP_TOKEN).
5. Agent POSTs to /api/v1/agents/enroll with:
   { "hostname": "...", "bootstrap_token": "...", ...metadata }
6. Server:
   a. Verifies bootstrap token hash exists, not consumed, not expired.
   b. Atomically marks it consumed (SET consumed_at, consumed_by_host_id WHERE id=? AND consumed_at IS NULL).
   c. If atomic update affects 0 rows → 409 TOKEN_ALREADY_USED.
   d. Creates Host record with status=ENROLLED.
   e. Issues long-lived agent credential (as today, shown once).
   f. Returns { host_id, agent_token, bootstrap_token_id }.
7. Agent stores host_id + agent_token in identity file (as today).
```

### 2.3 Agent Credential Lifecycle

- **Bootstrap token** (operator → agent, one-time): grants enrollment only. Never grants telemetry or command access. Expires in 10 minutes. Consumed atomically.
- **Agent credential** (server → agent, long-lived): grants telemetry, heartbeat, command poll/result for the enrolled host only. Revocable independently of the bootstrap token.
- **Rotation** (operator-initiated): server generates a new agent credential; old one remains valid for a configurable grace period (default: 5 minutes) then is invalidated. Agent must re-poll after rotation window; the agent loop handles `AuthError` exit today and will be extended to retry enrollment.
- **Revocation** (operator-initiated): `is_revoked=True`, old credential immediately invalid. Agent receives 401 on next heartbeat and must stop (as today, but with explicit operator action rather than re-enrollment).

### 2.4 Host Lifecycle State Machine

```
PENDING ────(enrollment complete)───> ENROLLED ────(first heartbeat)───> ONLINE
                                              │
                                              └──(revoked)───> REVOKED
                                                               ───(re-enroll)───> ENROLLED
                                                                               ───(heartbeat)───> ONLINE
ONLINE ────(no heartbeat > stale_threshold)───> STALE ────(no heartbeat > offline_threshold)───> OFFLINE
OFFLINE ────(heartbeat resumes)───> ONLINE
```

**State definitions:**
- `PENDING`: bootstrap token issued, enrollment not yet completed. No telemetry accepted.
- `ENROLLED`: credential issued, no heartbeat yet. Docker operations blocked.
- `ONLINE`: heartbeat received within stale threshold. Docker allowed if `docker_enabled=true`.
- `STALE`: heartbeat > 90s ago. Docker allowed (offline agents must complete in-flight ops).
- `OFFLINE`: no heartbeat > 600s. Docker allowed (agent may reconnect).
- `REVOKED`: credential invalid. All agent endpoints return 401. Host persists as tombstone (telemetry retained).

**Implementation**: add `enrollment_status: str NOT NULL DEFAULT 'PENDING'` to hosts table. Update `compute_status` to only apply heartbeat-based ONLINE/STALE/OFFLINE when status is ENROLLED or later.

### 2.5 Docker Ops Authorization

- **New hosts**: `docker_enabled: bool NOT NULL DEFAULT FALSE` on the Host model.
- **Phase 3B enrollment**: defaults to false.
- **Operator enables Docker** via a new `PATCH /api/v1/hosts/{id}` endpoint (operator-authenticated) setting `docker_enabled=true`.
- **Agent enforcement**: before executing Docker operations, agent sends a heartbeat; server response carries `docker_enabled` in `HeartbeatResponse`. Agent refuses Docker ops if `docker_enabled=false`.
- **Backend enforcement**: `deploy` service checks `Host.docker_enabled` before queueing `DEPLOY` operations. Returns `403 DOCKER_NOT_AUTHORIZED` if disabled.

### 2.6 Add Existing Server UX

```
Operator logs in
     │
     ▼
Clicks "Add Server" → "Existing server"
     │
     ▼
Dashboard calls POST /api/v1/operators/bootstrap-tokens
     │
     ▼
Server creates bootstrap token (displayed once in the UI with expiry warning)
     │
     ▼
Operator copies token to the target host and runs:
  NIMBUSOPS_AGENT_BOOTSTRAP_TOKEN=<token> nimbusops-agent
     │
     ▼
Agent enrolls; dashboard polls /api/v1/hosts and shows the new host appearing as ENROLLED/ONLINE
```

**Explicit confirmation**: after the host appears, a toast confirms enrollment with hostname and host_id. If enrollment fails, the error (token expired / already used / invalid) is shown in the UI.

**Failure states surfaced to operator:**
- `401 UNAUTHORIZED` (wrong token)
- `409 TOKEN_ALREADY_USED` (token consumed)
- `410 TOKEN_EXPIRED` (bootstrap token TTL exceeded)
- `503 ENROLLMENT_DISABLED` (no operator auth configured)
- `409 HOSTNAME_TAKEN` (hostname collision — requires operator to rename or revoke existing)

### 2.7 Safe Unregister UX

```
Operator navigates to host detail → "Unregister"
     │
     ▼
Dialog: "Unregister 'david-lab' ({host_id})? This will:
  - Revoke its agent credential immediately.
  - Stop accepting new telemetry and commands from this host.
  - Retain host history, telemetry, and audit records.
  - NOT delete Docker containers; remove them separately."
     │
     ▼
Operator types host_id to confirm (anti-accidental click)
     │
     ▼
Dashboard calls DELETE /api/v1/hosts/{id} (operator-authenticated)
     │
     ▼
Server: is_revoked=True, revoked_at=now. Host stays in DB as tombstone.
     │
     ▼
Agent receives 401 on next heartbeat → stops (as today).
Toast: "david-lab has been unregistered. Its history is preserved."
```

**DavidLab protection**: the dialog explicitly shows "This host is david-lab. Unregistering will prevent it from connecting." The server enforces `REVOKED` state before allowing any subsequent enrollment under the same hostname (enrollment with `is_revoked=true` requires re-enrollment via operator-issued bootstrap token, not unauthenticated re-enrollment).

---

## 3. Cross-Phase Isolation

### 3.1 Simulated Hosts

- Frontend `assertNotSimulated` guard in `client.ts:47-68` (Phase 3A, already implemented) remains active defense-in-depth.
- Phase 3B adds **backend enforcement**: `X-Host-Id` header values containing `sim-` are rejected with 400 at the `agents.py` router level (applied to heartbeat, telemetry, commands).
- No Phase 3B code paths accept or store simulated resource identifiers. Simulated hosts do not appear in any server-side table.

### 3.2 Preserving Phase 1/2 Behavior

- Public read endpoints (`/hosts`, `/hosts/{id}`, `/hosts/{id}/metrics`) remain unauthenticated in Phase 3B (trusted-local model).
- All agent endpoints retain existing `X-Host-Id` + Bearer auth pattern.
- `poll_commands` and `submit_command_result` behavior (atomic claim, first-write-wins, idempotent redelivery) unchanged.
- `deduplicated: true` behavior for in-flight operations unchanged.
- Phase 2 agent token format (256-bit `secrets.token_urlsafe`, stored as keyed SHA-256 hash) unchanged.

---

## 4. Design Decisions

**Status after review session 2026-11-10: O1, O6, O7 explicitly ACCEPTED by product owner; O2, O3, O4, O5, O8 accepted as defaults (proposed, unopposed). All eight are now binding for implementation.**

| ID | Decision | Options | Decision (accepted) |
|---|---|---|---|
| O1 | Operator auth method | Session cookies + CSRF; API key in env; OIDC gateway | **ACCEPTED** — Session token (Bearer), 256-bit, hashed at rest, TTL 12h; stored in-memory in the frontend (never localStorage); HttpOnly+SameSite cookie variant only when TLS is active |
| O2 | Bootstrap token delivery | Copy in UI; operator types into agent shell; secret manager | **ACCEPTED (default)** — shown once in UI with expiry countdown; operator pastes into agent env |
| O3 | Agent credential lifetime | Permanent (until revoked); rotatable | **ACCEPTED (default)** — permanent until revoked/rotated by operator |
| O4 | Credential rotation grace period | 0 (immediate); 5 min; 30 min | **ACCEPTED (default)** — 5 minutes, env-configurable |
| O5 | Enrollment token compatibility | Deprecate `NIMBUSOPS_ENROLLMENT_TOKEN` (Phase 4); keep as legacy bootstrap for existing hosts | **ACCEPTED (default)** — legacy path accepted during Phase 3B transition; removed no earlier than Phase 4 |
| O6 | DavidLab host migration | Auto-upgrade on first Phase 3B deploy; manual operator action | **ACCEPTED** — auto-upgrade: `enrollment_status='ENROLLED'`, `docker_enabled=false` via migration; existing credential keeps working; Docker stays locked until explicitly enabled |
| O7 | DB migration mechanism | Alembic; hand-written idempotent upgrade | **ACCEPTED** — Alembic, additive-only revisions (baseline + `0002_phase3b`) |
| O8 | Audit event schema | Append to existing `enrollment_audit`; add new `host_events` table | **ACCEPTED (default)** — new append-only `host_events` table (event/actor/detail); `enrollment_audit` retained for compatibility |
