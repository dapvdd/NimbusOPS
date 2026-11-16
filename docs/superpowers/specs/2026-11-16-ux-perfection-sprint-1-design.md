# NimbusOps — UX Perfection Sprint 1 (Design)

Date: 2026-11-16 · Branch: `sprint/ux-perfection` @ `8e2ba3b` · Status: revised through two builder reviews (v3), awaiting approval

## Intent

Make the console feel finished without ever lying. Consolidate the auth WIP, then
deliver a zero-friction enrollment path, truthful host lifecycle, persistent
service visibility, a single actionable dashboard, and a small design system that
makes every state legible.

The sprint is judged on one rule: **every control performs a real, authorized
backend operation, and every state is the backend's state.** No simulated
success, no fabricated telemetry, no "restart" that only animates.

## Evidence this design is built on

| Area | Current reality |
|---|---|
| CI | `.github/workflows/ci.yml` exists and is the quality contract: backend `pytest`, frontend `npm test`, `npx tsc -b`, `npx vite build` on PRs to `main` and pushes to `main`. Every slice must keep it green. |
| Status | `services/hosts.py:41` derives connectivity only; `api/public.py:26` puts it in `HostOut.status`. A revoked host with a recent heartbeat renders `ONLINE`; without one it renders `OFFLINE`. |
| Lifecycle | `services/host_lifecycle.py` implements rotate / revoke / re-enroll, and `api/host_lifecycle.py` exposes ADMIN-only endpoints. The frontend only calls revoke (`Servers.tsx`). `HostEvent` rows are written but no read endpoint exists. |
| Re-enroll | `agent/nimbusops_agent/main.py:46` returns the stored identity immediately and ignores a supplied bootstrap token. `deploy/examples/bootstrap-enroll.sh.example` refuses when the state file exists. The current "re-enroll" is therefore only a server-side token issuance, not a working repair path. |
| Enrollment | `api/bootstrap_tokens.py` issues single-use, hostname-scoped tokens (shown once). `services/enrollment.py:45` does not check whether the hostname already exists or whether an active token already exists. |
| Auth | `SessionProvider` uses cookie + CSRF (`browserLogin`), but `Servers.tsx:80` still calls the legacy bearer `api.login`. Two mechanisms coexist. |
| Simulation | `frontend/src/lib/simRegistry.ts` and `ServerDetail.tsx` render a browser-only registry with synthetic CPU/RAM. `Activity.tsx`, `ServerList.tsx`, and `Servers.tsx` import it. |
| Routing | `/hosts/:hostId` and `/servers/:hostId` both mount `ServerDetail`; `/deployments` and `/applications` both render the real deployments view; `/settings` is a placeholder. |
| Errors | `ApiFailure` carries only `kind`/`status`/`message`; `ErrorPanel` cannot show the stable `code` or a remediation. `readiness()` cannot use `request()` because 503 is the meaningful answer. |
| Design | Tailwind tokens exist (`ink`, `signal`, Inter) but primitives are ad hoc per view; status is a 3-state pill; dialogs are inline sections. |
| Baseline | Snapshot at `8e2ba3b`: 287 backend tests + 1 Windows-only skip, 58 frontend tests, build green. Reproduce with `.venv\Scripts\python -m pytest -q` and `npm test`. |

## Product truth rules (non-negotiable)

1. **REVOKED is terminal until re-enrollment.** Never display it as offline, never
   retry with the revoked credential, never hide it from the fleet. Ship the
   `StatusBadge` fallback in the same commit as the status widening, so no
   intermediate commit can render a `REVOKED` host through a 3-state badge.
2. **Missing is not zero.** No telemetry → `—`, not `0%`. No heartbeat → `never`.
3. **No optimistic success.** A flow advances only after the backend confirms it.
   Token issuance is real; enrollment completion means the token is consumed,
   the host exists, and a heartbeat has arrived.
4. **Destructive and privileged actions are ADMIN-only and confirmed.**
   Revoke, rotate, re-enroll, and enabling Docker execution require explicit
   confirmation; revoke requires typing the hostname.
5. **Secrets exist once, in memory, and never in argv, URLs, logs, or storage.**
   Bootstrap and rotation tokens reach the host via a `0600` file whose contents
   are typed at a prompt (or piped from a paste); new agent tokens are displayed
   once in a transient panel and cleared when the panel closes.
6. **A button that cannot do the thing is worse than no button.** Installation and
   remote service control are not executable from the browser, so the UI provides
   copyable, parameterized commands and live verification instead of fake controls.
7. **VIEWER is read-only.** No lifecycle, enrollment, deployment, or Docker
   controls are rendered at all (not merely disabled).

## Decisions

### D1 — Effective status lives on the backend

Keep `compute_status()` as the pure connectivity function (existing tests and the
agent protocol keep working) and add:

```python
def effective_status(*, is_revoked: bool, enrollment_status: str,
                     last_seen_at, now, stale_s, offline_s) -> str:
    if is_revoked or enrollment_status == "REVOKED":
        return "REVOKED"
    return compute_status(last_seen_at, now, stale_s, offline_s)
```

`HostOut` changes (all additive except the widened `status` literal):

```jsonc
{
  "status": "ONLINE | STALE | OFFLINE | REVOKED", // effective, for display
  "connectivity": "ONLINE | STALE | OFFLINE",     // heartbeat only
  "agent_mode": "executor | telemetry-only | null",
  "credential_version": 1,
  "credential_grace_until": "2026-11-16T10:05:00Z | null",
  // unchanged: is_revoked, enrollment_status, docker_enabled, ...
}
```

- `credential_grace_until` is `null` unless `previous_token_hash` is set **and**
  `previous_token_expires_at > now`; the UI never counts down a dead grace window.
  (The `previous_token_*` columns and grace semantics already exist in
  `authenticate_host`, `hosts.py:188-214`; only the exposure is new.)
- `enrollment_status` stays the raw lifecycle column and is documented as
  non-display state.
- Agent-facing heartbeat/telemetry responses keep returning connectivity; a
  revoked agent never reaches them (`authenticate_host` rejects first with
  401 `HOST_REVOKED`).
- Old clients that switch on `ONLINE|STALE|OFFLINE` continue to work for live
  hosts; revoked hosts are now correctly distinct. `docs/API.md` is updated.
- **PENDING is deliberately not a `HostOut.status`.** No `Host` row exists before
  enrollment (`enroll_host` writes `ENROLLED`), so a `PENDING` host status would
  require a phantom row. "Awaiting enrollment" is derived from bootstrap-token
  lifecycle (D2) and displayed as a first-class fleet row. The model default is
  corrected from `PENDING` to `ENROLLED` because every persisted row is created
  enrolled; `PENDING` stays in the response literal for legacy/contract reasons.

### D2 — Onboarding state is derived from the token, not invented

No new onboarding-token endpoint is introduced. The wizard and fleet view read the
existing ADMIN-only `GET /api/v1/operators/bootstrap-tokens` (with the new
`?active=true&limit=`) plus `GET /api/v1/hosts` and derive:

```ts
type OnboardingState = "WAITING" | "EXPIRED" | "CONSUMED" | "REVOKED";
// WAITING  = no consumed_at, no revoked_at, expires_at > now
// EXPIRED  = no consumed_at, no revoked_at, expires_at <= now
// CONSUMED = consumed_at != null (host may or may not have heartbeated yet)
// REVOKED  = revoked_at != null and not consumed
```

A `useOnboarding()` hook owns this derivation. A row is shown only for tokens
whose hostname has no live host row, or whose host is revoked (repair context), so
the fleet is never double-counted. VIEWER never calls the token endpoint and sees
only real hosts.

**Server-side guards are mandatory**, because client checks are advisory:

- `POST /operators/bootstrap-tokens` gains `intent: "enroll" | "reenroll"`
  (default `enroll`), persisted on the `bootstrap_tokens` row (additive column).
- The guard is enforced **again at consumption**, inside the enrollment
  transaction, not only at issuance:
  - `enroll`: reject `409 HOSTNAME_TAKEN` when any host with that hostname
    exists, revoked or not. Revoked/repair cases must use `reenroll`.
  - `reenroll`: require an existing host with that hostname, else
    `404 HOST_NOT_FOUND`; this is the only path allowed to un-revoke.
  - A token issued while no host existed cannot silently rotate a host that
    appears later: consumption re-checks the intent.
  - The intent/host check runs **before** the consuming `UPDATE`, in the same
    transaction as host creation, so a rejected re-enroll (wrong intent, missing
    host, hostname mismatch) never burns the token. Token rows created before this
    change migrate to `intent="enroll"`; re-enrolling an existing host therefore
    requires a freshly issued `reenroll` token, which is exactly what the console
    issues.
- At most one active token per hostname, enforced atomically by a partial unique
  index on `(hostname) WHERE consumed_at IS NULL AND revoked_at IS NULL`.
  Issuance first revokes any expired active token for that hostname, then inserts;
  an `IntegrityError` maps to `409 BOOTSTRAP_TOKEN_ACTIVE`. The wizard and the
  re-enroll dialog handle that code by refetching the ADMIN token list, matching
  the hostname, and offering "Revoke and reissue" (DELETE then POST). The error
  envelope stays `{code,message}`; no `details` field is added.
  If a legacy DB already holds duplicates, index creation is skipped with a
  warning (same fail-safe pattern as the in-flight operation index) and the
  serialized check still prevents new duplicates.
- `POST /hosts/{id}/re-enroll` always uses `intent="reenroll"`.
- Hostnames are normalized (`strip().lower()`) at issue and consumption, and host
  lookup is case-insensitive, so `host-1` and `HOST-1` cannot become two
  identities. A mismatch raises a distinct `BOOTSTRAP_TOKEN_HOSTNAME_MISMATCH`
  with "the token was issued for `<expected>`; this host reports `<actual>`" so
  the operator can correct the name (recommended: `hostname -f`) instead of
  burning tokens.
- `GET /operators/bootstrap-tokens` gains `?active=true&limit=` (default 50) so
  `useOnboarding` does not pull the whole token history.

### D3 — Reported agent mode, not guessed mode

Add an optional `agent_mode: "executor" | "telemetry-only"` to the heartbeat
payload, persist it in a new **nullable** `hosts.agent_mode` column through the
existing additive migration mechanism, and expose it on `HostOut`.

Semantics: every heartbeat writes the mode the current process reports, including
`None` when an older agent omits it. A mode is therefore "reported by the running
agent", not a stale value from a previous binary. The UI also shows heartbeat age.

| `docker_enabled` | `agent_mode` | Display |
|---|---|---|
| false | any/null | `Monitoring only — Docker permission off` |
| true | `telemetry-only` | `Monitoring only — agent reports telemetry-only` |
| true | `executor` | `Docker execution enabled` |
| true | null | `Docker permission on — agent mode not reported (older agent)` |

Agent path is `agent/nimbusops_agent`. `run_cycle` adds `info["agent_mode"]` before
`Sender.send_heartbeat`; `touch_heartbeat` persists it. No enrollment-protocol
change is required.

### D4 — Service management is visibility + safe delegation, not remote control

The backend and agents run as OS services on machines this browser does not own.
The sprint delivers:

- **Control plane panel** (Settings): live `/health` + `/ready`, version/build,
  database state, latency, last check, manual recheck, and recovery steps. No
  "restart backend" button, because a browser cannot truthfully restart it.
- **Agent runtime panel** (host detail): reported mode, Docker permission,
  credential version, grace deadline, last heartbeat/telemetry, and the exact next
  action (e.g. re-enroll). Service state is read from what the backend knows
  (heartbeat, reported mode, Docker permission) — the browser never invents a
  "running/stopped" claim about a remote OS service.
- **Copyable service definitions**: command templates generated from the committed
  `deploy/examples/` contract, with substitutions explained. The UI states clearly
  that it generates commands; it does not claim they ran. It does not link to a
  non-existent web route for repo files.
- **Credential delivery helpers** (D6) that make rotation and re-enrollment
  actually completable on a real host.

Actual installation, remote restart, and multi-host systemd validation remain
infrastructure work requiring separate approval.

### D5 — One fleet, one route shape

- `/servers` — fleet (real hosts + derived onboarding rows; search/status filter).
- `/servers/new` — onboarding wizard (full page, not a modal; commands need room).
- `/servers/:hostId` — detail with tabs `overview | monitoring | deployments | activity`.
- `/hosts/:hostId` — redirect to `/servers/:hostId` (old links, tests).
- `/` — dashboard; `/deployments` and legacy `/applications` both render the real
  deployments view; `/activity`; `/settings`.

`/servers/new` is declared **before** `/servers/:hostId`, otherwise the wizard is
captured as a host id.

Remove the simulated registry and every "SIMULATED" branch. Keep the server-side
`SIMULATED_HOST_REJECTED` guard and the client-side `sim-` mutation guard as
defense in depth (no UI path can produce such an id anymore).

### D6 — Re-enroll and rotation are completable, and the UI says how

**Re-enroll (repair, works for revoked or lost credentials).** Server keeps the
host row and id; the agent replaces its local credential. `--reenroll` is a
**one-shot** maintenance command: it enrolls, saves the new identity, and exits 0.
It is not the steady-state service command. The steady-state unit never passes it.

```sh
# On the host. STATE must equal the unit's StateDirectory.
STATE=/var/lib/nimbusops-agent
sudo install -d -m 0700 -o nimbusops -g nimbusops "$STATE"

# Type the token as the service account; it is never in the command line.
sudo -u nimbusops bash -c '
  umask 077
  read -rsp "Bootstrap token: " t; echo
  printf "%s" "$t" > "$1/bootstrap.token"
  unset t
' _ "$STATE"

sudo systemctl stop nimbusops-agent
sudo -u nimbusops /opt/nimbusops/venv/bin/python -m nimbusops_agent \
  --reenroll \
  --bootstrap-token-file "$STATE/bootstrap.token" \
  --server-url https://ops.example.internal \
  --state-file "$STATE/agent.json"
# exits 0 only after enrollment succeeded and the new identity was written
rm -f "$STATE/bootstrap.token"
sudo systemctl start nimbusops-agent
```

New agent flag `--reenroll`:
- is one-shot; it does **not** enter the monitoring loop;
- requires a **bootstrap** token (file/env), never argv; a legacy
  `enrollment_token` is rejected because the legacy path cannot re-enroll;
- backs up the existing identity to `agent.json.pre-reenroll-<utc>` (0600) before
  enrolling, restores it and exits `2` on failure, and deletes the backup only
  after a confirmed enrollment;
- writes the new identity atomically using the existing atomic `save_identity`
  path; the server host id is unchanged because the hostname matches and the token
  is consumed (the `reenroll` intent also clears `is_revoked` server-side);
- after a confirmed enrollment, verifies one heartbeat with the new credential
  before reporting success, so "re-enroll complete" means the host is actually
  talking to the server again;
- only an explicit `--reenroll` bypasses the stored identity. Normal startup still
  refuses to re-enroll with an existing identity, so credentials are never
  replaced by accident.

The wrapper (`NIMBUSOPS_AGENT_ACTION=reenroll`) requires the state file to exist,
skips the fresh-enrollment "must not exist" guard, passes `--reenroll`, and exits
with the agent's code; it is a maintenance script, not a long-running service. A
systemd operator may use it in a dedicated one-shot unit and then start the normal
unit, or run the commands above. `Restart=on-failure` on the steady-state unit is
unaffected.

The UI explains the local identity replacement in plain language and polls
`GET /hosts/{id}` until `credential_version` increases, `is_revoked` is false, and
`last_seen_at` advances. `RE_ENROLLED` is a host event, not a status field; it is
shown in the new history panel, not used as a poll exit condition.

**Rotate credential (planned replacement, grace window).** Rotation returns a new
agent token and keeps the old one valid for the grace period. New agent flag
`--apply-credential-file` is one-shot: it verifies the candidate token against the
API, then updates the existing identity atomically and exits 0 (restart the
service afterwards).

```sh
STATE=/var/lib/nimbusops-agent
sudo -u nimbusops bash -c '
  umask 077
  read -rsp "New agent token: " t; echo
  printf "%s" "$t" > "$1/credential.next"
  unset t
' _ "$STATE"

sudo -u nimbusops /opt/nimbusops/venv/bin/python -m nimbusops_agent \
  --apply-credential-file "$STATE/credential.next" \
  --state-file "$STATE/agent.json"
sudo systemctl restart nimbusops-agent
```

`--apply-credential-file`:
- refuses if the candidate path resolves to the state file, or if no identity
  exists (use enroll/re-enroll instead);
- validates the token shape before touching anything;
- writes `agent.json.pre-apply-<utc>` (0600), sends one heartbeat with the
  candidate token (including the configured `agent_mode` so verification does not
  clear a reported mode), and only on success replaces the identity and deletes
  both the candidate file and the backup; on `401/403` it keeps the old identity
  and the candidate file, and exits `3`; on a network error it keeps everything
  and exits `1`.
- never prints the token, and never places it in argv or an environment dump.

The UI shows a grace countdown and a hard warning that the host must be updated
before it ends; if it is missed, the only recovery is re-enroll. There is no
"credential updated" claim until the verified heartbeat succeeds and the service
reconnects.

## Detailed design

### 1. Fleet (`/servers`)

Header: title, count, `Add server` (ADMIN), refresh. Below: status filter chips
(`ALL`, `ONLINE`, `STALE`, `OFFLINE`, `REVOKED`, `AWAITING`), environment filter,
and search.

Rows (cards on narrow, table on wide) contain only real data:

- hostname (link), effective `StatusBadge`, environment, reported agent mode.
- last contact age (heartbeat + telemetry separately), CPU/RAM/Disk or `—`.
- ADMIN row actions: `Manage` (detail), `Re-enroll` (revoked only), `Revoke`.
- Onboarding rows: hostname, `AWAITING`/`EXPIRED`, token expiry countdown, no
  metrics, actions `View instructions`, `Reissue`, `Cancel`. A `CONSUMED` token
  with no host row (only possible from a pre-transaction historical record) is
  shown as `CONSUMED — host record missing` with a link to the operator notes,
  never as a waiting row.

Empty state: "No servers yet" + real CTA `Enroll your first server`. Error state:
`ErrorPanel` with code-specific guidance. Loading: skeleton rows, not a spinner
that hides prior data.

### 2. Onboarding wizard (`/servers/new`)

An ADMIN-only, five-step flow whose state is derived from backend responses:

1. **Host** — hostname (trimmed, 1–255, lowercase hint). On submit, check the
   existing fleet: an exact hostname match routes to "This host already exists"
   with `Re-enroll` / `Open host`, instead of silently rotating a credential. The
   server enforces the same rule (D2).
2. **Mode** — `Telemetry only (recommended)` vs `Docker executor`. Explains that
   executor mode needs Docker access on the host and that `docker_enabled` is a
   separate, default-off permission granted after enrollment.
3. **Token** — real `POST /operators/bootstrap-tokens` with `intent="enroll"` and
   the hostname. Shows the token once, expiry countdown, copy button, and "This
   token cannot be shown again". `Reissue` revokes the previous unconsumed token
   first (handling `BOOTSTRAP_TOKEN_ACTIVE` explicitly).
4. **Install** — generated commands using `window.location.origin`, with the token
   **typed at a prompt into a 0600 file**, never interpolated into the command:

   ```sh
   sudo install -d -m 0700 -o nimbusops -g nimbusops /var/lib/nimbusops-agent
   sudo -u nimbusops bash -c '
     umask 077
     read -rsp "Bootstrap token: " t; echo
     printf "%s" "$t" > /var/lib/nimbusops-agent/bootstrap.token
     unset t'
   ```

   Tabs: `systemd (recommended)` and `foreground`. The systemd tab shows the full
   environment contract (`NIMBUSOPS_INSTALL_DIR`, `NIMBUSOPS_SERVER_URL`,
   `NIMBUSOPS_TOKEN_FILE`, `NIMBUSOPS_STATE_FILE`, `NIMBUSOPS_AGENT_MODE`), then
   runs `deploy/examples/bootstrap-enroll.sh.example`. The foreground tab runs
   `python -m nimbusops_agent --bootstrap-token-file ...`. Paths in the text are
   plain references, not runtime links.

5. **Verify** — a live checklist driven by polling (3 s while visible, paused
   when hidden): token consumed → host appears → first heartbeat → first
   telemetry. `Continue to host` is enabled only when the host exists. If the
   token expires first, the page switches to `EXPIRED` with a single `Issue a new
   token` action. Leaving the page cancels nothing server-side; the token remains
   until expiry or explicit cancel. This page is a wizard route (ADMIN), so
   VIEWERs never reach it and never see token material.

Rules: the token lives only in component state; it is cleared on unmount, on
reissue, and on success. No `localStorage`, no URL, no console. Clipboard failure
is reported honestly ("Select and copy manually"). The command never contains the
token; copying it to the clipboard is the user's explicit action.

### 3. Host detail and lifecycle

Top: hostname, effective status, environment, agent mode, Docker permission,
"last contact" summary, and a **REVOKED banner** when applicable (revoked time,
what still works, primary action `Re-enroll this host`).

Tabs keep the existing structure; Overview adds an **Agent runtime** panel:

- reported mode and Docker permission with the D3 truth table;
- credential version and, when a rotation grace window is open, a live countdown;
- last heartbeat / telemetry / enrollment time;
- mode-specific guidance (e.g. "telemetry-only: Docker operations will not run").

Actions (ADMIN only, all real endpoints):

| Action | Endpoint | Confirmation | Success UI |
|---|---|---|---|
| Edit environment | `PATCH /hosts/{id}` `{environment}` | Single confirm (metadata only) | Fleet chips/filters update after refetch |
| Enable Docker execution | `PATCH /hosts/{id}` `{docker_enabled:true}` | Dialog explains execution risk | Permission flips only after refetch |
| Disable Docker execution | same, `false` | Single confirm | Refetch |
| Rotate credential | `POST /hosts/{id}/rotate-credential` | Grace choice 0/300/900/3600 s + warning | Token shown once + `--apply-credential-file` steps + grace countdown |
| Re-enroll / repair | `POST /hosts/{id}/re-enroll` | Explains local identity is replaced, server identity is kept | Token once + `--reenroll` steps + poll on `credential_version` |
| Revoke / unregister | `DELETE /hosts/{id}` | Type the hostname; consequences list | Row becomes REVOKED; no redirect, no deletion |

Blocked states:

- Revoked: rotate, Docker, and environment actions are absent; only `Re-enroll`
  and history.
- Agent not reporting: Rotate/Re-enroll remain available (repair), with copy that
  says the host must run the command before the token/grace expires.
- VIEWER: no action controls at all.

No `window.confirm`; dialogs are accessible components with focus trap, Escape,
restore-focus, `aria-modal`, and a typed-confirmation field for revoke.

**History panel**: new `GET /api/v1/hosts/{id}/events?limit=50` returns the
existing `HostEvent` rows (`at`, `event`, `actor`, `detail`) for operator sessions
(VIEWER allowed). `detail` never contains token material. This replaces
"Full audit history: NOT IMPLEMENTED" and makes re-enroll/rotate outcomes visible.

### 4. Dashboard (`/`)

A decision surface, not a decoration. The current `Overview.tsx` already counts
`ONLINE/STALE/OFFLINE` (`Overview.tsx:50-52`) and renders per-host rows with
honest metric fallbacks; the sprint extends it with the REVOKED/AWAITING counts,
the attention list, and the control-plane status.

1. **Fleet strip** — counts by effective status plus `AWAITING`; each count links
   to the filtered fleet.
2. **Needs attention** — real rows only:
   - revoked hosts,
   - stale/offline hosts,
   - onboarding tokens expiring in < 5 minutes or already expired,
   - `docker_enabled=true` with `telemetry-only`/unknown agent mode,
   - degraded control plane (from `/health`).
   Each entry has the one action that resolves it.
3. **Fleet table** — compact version of the fleet rows, sorted by attention.
4. **Recent operations** — last 5 real operations with status and error code;
   link to Activity.

No synthetic counters, no "all systems operational" claim unless `/health` says
`ok` and no host needs attention.

### 5. Settings (`/settings`)

- **Account**: username, role, sign out (real session endpoint).
- **Control plane**: health/readiness, version/build, DB state, latency, last
  check, recheck. If degraded, show concrete checks (process, database path,
  logs) instead of a restart button.
- **Deployment reference**: copyable unit paths and the environment contract;
  explicit "not installed by NimbusOps" note. Plain text references, no dead app
  routes.
- **Control-plane polling**: `/health` and `/ready` are the only unauthenticated
  API paths (backed by `require_read`), so the panel works before and after
  sign-in; everything else on the page requires the session. `/ready` returns a
  meaningful 503 body, which the client must read rather than throw on.
- **Appearance**: display-only note in Sprint 1 (dark theme is the product); no
  fake theme switch.

### 6. Errors and recovery

`ApiFailure` gains `code?: string` and `retryable: boolean` (derived from
status/code, not a wire field). The parser reads
`{"error":{"code","message"}}`; network failures keep `kind:"network"`.
Validation (422) stays FastAPI's shape and is summarized without leaking input.

`frontend/src/lib/errorGuidance.ts` maps codes to `{title, detail, action?, surface}`
where `surface` is `browser`, `operation`, or `agent`:

| Code | Surface | Guidance |
|---|---|---|
| `HOST_REVOKED` | browser/operation | "This host's credential is revoked. Re-enroll to reconnect." → re-enroll |
| `HOST_NOT_FOUND` | browser | "This host no longer exists." → fleet |
| `BOOTSTRAP_TOKEN_EXPIRED/CONSUMED/INVALID` | browser | "This enrollment token is no longer usable." → issue a new token |
| `BOOTSTRAP_TOKEN_ACTIVE` | browser | "Another enrollment token is still active." → revoke and reissue |
| `BOOTSTRAP_TOKEN_HOSTNAME_MISMATCH` | browser/agent | "The token was issued for a different hostname." → correct the hostname, reissue |
| `HOSTNAME_TAKEN` | browser | "That hostname is already enrolled." → open the host or re-enroll |
| `OPERATOR_AUTH_REQUIRED` | browser | "Your session expired." → sign in (preserve return path) |
| `OPERATOR_FORBIDDEN` | browser | "Your role cannot perform this action." (no retry) |
| `RATE_LIMITED` | browser | "Too many requests. Retry shortly." (retryable) |
| `INVENTORY_NOT_FOUND` | browser | "No Docker inventory has been reported yet." (not an error state) |
| `DOCKER_NOT_AUTHORIZED` | operation | "Docker execution is disabled for this host." → host settings |
| `DOCKER_UNAVAILABLE` / `DOCKER_FAILURE` | operation | "The host could not reach Docker." → host agent check |
| `AGENT_UNREACHABLE` / `TIMEOUT` | operation | "The agent did not respond in time." → retry + re-enroll if persistent |
| `ENROLLMENT_DISABLED` / `ENROLLMENT_MODE_CONFLICT` | agent | Shown in agent logs/runbook, not as a browser failure |
| `FORBIDDEN_HOST` / `SIMULATED_HOST_REJECTED` | browser | "This identifier is not a real host." (client guard; unreachable through the new UI) |
| network | browser | "Cannot reach the API." + check service/URL/proxy |

`ErrorPanel` renders title, human message, code (monospace, selectable),
remediation, retry, and secondary actions. It never renders tokens, request
bodies, or raw server internals. `InlineAlert` is used for section-level errors so
a single failed panel does not blank the page. Operation failures use the same
guidance map against `Operation.error_code`.

### 7. Design system

A light-weight system on the existing Tailwind setup; no new UI dependency.

**Tokens** (`tailwind.config.js` + `src/index.css`):

- Surfaces: `ink-950/900/850/800/700` retained; add semantic aliases
  `surface-0..3`, `border-subtle`, `border-strong`.
- Signals: `ok`, `warn`, `bad`, `info`, plus `revoked` (neutral violet/slate) and
  `pending` (info-blue).
- Type: Inter; scale 11/12/14/16/20/24/30; tabular numerals for metrics; mono for
  IDs/tokens/commands.
- Radius 8/12/full; 1px borders; no heavy shadows; 4px spacing grid.
- Focus: 2px `--focus` ring with 2px offset, always visible on keyboard focus.

**Primitives** (`src/ui/`): `Button`, `IconButton`, `Card`, `Panel`, `Field`,
`Dialog`, `InlineAlert`, `StatusBadge` (extended in place in slice 1, moved to
`src/ui/` in slice 3 with a re-export from the old path), `CopyField`,
`DescriptionList`, `Tabs`, `Skeleton`, `Toast` (`aria-live="polite"`), `Kpi`.

**Status semantics**: color + text + icon, never color alone.

| Status | Label | Tone | Icon |
|---|---|---|---|
| ONLINE | Online | green | filled dot |
| STALE | Stale | amber | half dot |
| OFFLINE | Offline | red | hollow dot |
| REVOKED | Revoked | violet/slate | lock/ban |
| AWAITING | Awaiting enrollment | blue | spinner-dot |
| EXPIRED | Token expired | amber | clock |
| Unknown (defensive) | Unknown | neutral | question |

`StatusBadge` must not crash on an unknown value once the union widens; the
slice-1 fallback ships with the widening (truth rule 1).

**Rules**: one primary action per panel; destructive actions use the danger
variant; disabled state only when the action is genuinely unavailable, with an
adjacent reason; loading buttons keep width and announce `aria-busy`.

**Motion**: 120–180 ms fades/translates only; `prefers-reduced-motion` disables
them. No pulsing status except an actual pending check.

### 8. Accessibility

- Every icon-only control has an accessible name; every form control a label.
- Dialogs trap focus, close on Escape, restore focus, and are labelled by title.
- Async results announce via `role="status"` / `aria-live`; errors via `role="alert"`.
- Tabs follow `aria-selected` + `role="tabpanel"` (existing pattern retained).
- Minimum 44×44 px targets on touch; visible focus; AA contrast on dark surfaces.
- Status is conveyed by text, not only color; countdowns do not rely on animation.
- Keyboard-only path for onboarding (copy buttons included) is part of the test plan.

## Backend changes (minimal, additive)

1. `services/hosts.py`: add `effective_status(...)`; keep `compute_status(...)`;
   persist `agent_mode` in `touch_heartbeat` (write the reported value, including
   `None`); correct `Host.enrollment_status` default to `ENROLLED` and update the
   model comment; flush the host before recording the `ENROLLED` event so a fresh
   host's history is not empty.
2. `schemas/__init__.py`: widen `HostOut.status`; add `connectivity`, `agent_mode`,
   `credential_version`, `credential_grace_until`; add optional `agent_mode` to
   `HeartbeatRequest`; add `environment` to `HostPatchRequest`; add `intent` to
   the bootstrap-token request.
3. `api/public.py`: populate the new fields from the host row.
4. `api/agents.py`: pass the consumed token's intent into enrollment; no
   response-shape change beyond the existing status.
5. `models.Host`: nullable `agent_mode`; `models.BootstrapToken`: `intent`
   (`enroll`/`reenroll`); `core/migrations.py`: additive columns (no backfill;
   `agent_mode` legacy = unknown, `intent` legacy = `enroll`) plus the partial
   unique active-token index with the fail-safe skip on legacy duplicates.
6. `services/enrollment.py`: normalize hostname at issue/consume; enforce intent
   at consumption inside the transaction (existing host required for `reenroll`,
   forbidden for `enroll`, revoked included); one-active-token guard; revoke
   expired active tokens before insert; new `BOOTSTRAP_TOKEN_ACTIVE` and
   `BOOTSTRAP_TOKEN_HOSTNAME_MISMATCH` codes in `core/codes.py`;
   `issue_bootstrap_token` gains an intent parameter so the re-enroll service and
   the API share one guard implementation.
7. `api/host_lifecycle.py`: `PATCH` accepts `environment` (validated, recorded as
   `ENVIRONMENT_CHANGED` in `HostEvent`); add
   `GET /hosts/{id}/events?limit=` mounted on the read-protected public router
   (operator session, VIEWER allowed, newest first).
8. `api/bootstrap_tokens.py`: `?active=true&limit=` filter for the onboarding hook.
9. `deploy/examples/bootstrap-enroll.sh.example`: `NIMBUSOPS_AGENT_ACTION=reenroll`
   path that runs the one-shot and exits; steady-state behavior unchanged.

No new tables, no destructive migration, no change to deployment or operation
protocols. Existing databases and host identities remain valid.

## Frontend changes (surface map)

- Remove the legacy bearer path: `api.login`/`api.logout`,
  `operatorSessionToken`, `currentSessionToken`, and `authHeaders` bearer
  injection. The console uses cookie session + CSRF only (`Session.tsx` +
  `resolve_request` already prefer the cookie, so behavior is unchanged for
  signed-in users; only the duplicated path and its tests are removed). The
  inline login inside `Servers.tsx::EnrollFlow` is deleted; the wizard relies on
  the existing `SessionProvider`/`Protected` gate. Update `docker.host.test.tsx`,
  `enrollment.test.tsx`, and `servers.test.tsx` in the same slice.
- Delete `lib/simRegistry.ts` only after its last import is gone; remove imports
  from `Servers`, `ServerDetail`, `Activity`, `ServerList`, `auth.test.tsx`, delete
  synthetic branches, and delete `simRegistry.test.ts` with the source.
- `api/types.ts`: `HostStatus` widened; new fields; `OnboardingState` type. The new
  host fields (`connectivity`, `agent_mode`, `credential_version`,
  `credential_grace_until`) are optional in the TS type (backend always sends
  them once shipped, but optional keeps existing fixtures valid and tests honest
  about which fields a view actually reads).
- `api/client.ts`: parse `code`; add `readiness()` that treats HTTP 503 as data
  (`fetch` directly or an `allowStatus` option), add `listHostEvents`, and pass
  `?active=true&limit=` for onboarding tokens.
- `lib/errorGuidance.ts`, `lib/onboarding.ts` (derive state + commands),
  `lib/agentCommands.ts` (templates copied from the documented `deploy/examples`
  contract; no token interpolation), `hooks/useOnboarding.ts`, `hooks/useFleet.ts`
  (single polling source).
- `ui/` primitives; `components/StatusBadge.tsx` extended with a defensive
  fallback (ships in slice 1 with the status widening, so a `REVOKED` value can
  never crash the current UI); `StatePanels.tsx` rewritten to accept `ApiFailure`
  and guidance.
- `views/Servers.tsx` rewritten (fleet + filters + onboarding rows). Its inline
  `EnrollFlow` (with the legacy `api.login` form) is deleted; the wizard becomes
  the only enrollment surface.
- `views/Onboarding.tsx` (new wizard).
- `views/HostDetail.tsx` extended (runtime panel + lifecycle dialogs + history);
  `HostActions.tsx`, `CredentialDialogs.tsx`, `ConfirmDialog.tsx` extracted.
  The re-enroll dialog handles `BOOTSTRAP_TOKEN_ACTIVE` by refetching the token
  list, matching the hostname, and offering revoke-and-retry.
- `views/ServerDetail.tsx` simplified to real hosts + tabs.
- `views/Overview.tsx` rewritten as the dashboard.
- `views/Settings.tsx` (new).
- `views/Applications.tsx`: hide deploy/start/stop for VIEWER (today they are only
  disabled); branch status copy so REVOKED says "re-enroll required", not "will run
  when the agent reconnects" (`Applications.tsx:297-301`). The same revision covers
  `HostDetail.tsx:104-113`, whose "Agent status" row falls through to "Not
  reporting" for a revoked host; the pinned assertion in
  `views.test.tsx:189` ("Not reporting") stays valid for a genuinely
  offline, non-revoked host and a new case pins the revoked copy.
- `App.tsx` routes as D5 (including `/applications` alias); `Sidebar.tsx` and
  `ServerList.tsx` real-only, effective-status dots/labels (REVOKED is not the
  offline dot).
- `Activity.tsx` real operations only; no simulated history.
- Grep every `status ===` consumer before closing the slice; `HostDetail`'s
  "Agent status" row must say "Credential revoked" when revoked (fall-through
  today), and the fleet's revoked copy must not reuse the offline wording.

## Verification plan

**CI contract (must stay green)**

`.github/workflows/ci.yml` runs `python -m pytest -q`, `npm test`, `npx tsc -b`,
and `npx vite build`. Each commit must keep all four green. The E2E harness below
is an addition, not a replacement.

**Backend (must pass)**

- `effective_status`: revoked beats fresh heartbeat, stale, offline, and never-seen;
  non-revoked hosts are unchanged; `REVOKED` in `enrollment_status` alone also wins.
- `HostOut` serializes `status/connectivity/agent_mode/credential_version/
  credential_grace_until`; grace is `null` when inactive or expired.
- Heartbeat persists `agent_mode`; omission clears it to `null`; invalid value is
  rejected by the schema; older payloads remain valid. A fresh host's `ENROLLED`
  event is visible immediately (the host row is flushed before the event is
  recorded).
- `PATCH` environment: valid values persist, invalid values are rejected, and the
  change writes an `ENVIRONMENT_CHANGED` `HostEvent` with the actor and old/new
  value.
- Bootstrap guards, issuance **and** consumption:
  - `intent=enroll` rejects an existing hostname, including a revoked one;
  - `intent=reenroll` requires an existing hostname and is the only path that
    un-revokes;
  - a token issued before a host existed cannot later rotate it;
  - hostname normalization: `Host-1` at issue and `host-1` at consumption match;
  - `BOOTSTRAP_TOKEN_HOSTNAME_MISMATCH` reports expected vs actual without
    consuming the token.
- Active-token uniqueness: a second active token for one hostname returns
  `BOOTSTRAP_TOKEN_ACTIVE`; revoking the first then reissuing succeeds; the partial
  unique index is created once, and on a legacy DB with duplicates the migration
  warns and skips instead of failing startup.
- Rejected guards never burn a token: after a `HOSTNAME_TAKEN`/intent rejection,
  the token can still be consumed by the correct flow.
- Host events endpoint returns newest-first, honors `limit`, contains no token
  material, and is readable by VIEWER (read-only). It is mounted on the
  read-protected router (`require_read`), matching `GET /hosts`; the
  `authenticated_reads` conftest fixture must list its test module so existing
  read-contract tests keep passing.
- Agent one-shot flags: `--reenroll` exits 0 only after a saved identity **and one
  verified heartbeat** with the new credential, backs up and restores on failure
  (exit 2), and never enters the loop; `--apply-credential-file` rejects a missing
  identity or a candidate path equal to the state file, verifies the candidate
  with a heartbeat, and only then replaces the identity
  (401/403 → exit 3, keep everything; network → exit 1). Neither ever places a
  secret in argv or logs.
- Migration idempotence on a legacy DB: `agent_mode` and `intent` added once,
  existing rows and credentials untouched.
- Existing suite green, plus new tests. One existing web test pins a comment that
  no longer matches the model and is refreshed in the same slice:
  `test_migration.py::test_new_host_defaults_pending_and_docker_disabled` already
  asserts `ENROLLED` (line 47) but its docstring still says "defaults to PENDING";
  the docstring is the only change needed. `test_rc2_enrollment_contract.py::
  test_bootstrap_reenroll_rotates_with_stable_identity` issues its second token
  without an intent, which the new guard rejects (`HOSTNAME_TAKEN`); that test
  must issue with `intent="reenroll"`, exactly as the console's re-enroll dialog
  does. `test_host_lifecycle` keeps exercising `POST /hosts/{id}/re-enroll`, which
  sets that intent; its "host still revoked until the agent consumes" assertion
  remains the pin for the un-revoke-on-consume rule.

**Frontend (must pass)**

- `StatusBadge` covers all states and fails closed to "Unknown" (no crash).
- Fleet renders a revoked host as `REVOKED` with re-enroll, never as `OFFLINE`,
  and never shows synthetic metrics.
- Onboarding: token only after a real POST; generated commands contain no token
  and no `--token`; "waiting" persists until consumed+host; expiry offers reissue;
  `BOOTSTRAP_TOKEN_ACTIVE` offers revoke-and-reissue. The current
  `Servers.tsx` token panel (lines 104-113) tells the operator to "run the agent
  with this token in its environment" — the wizard replaces that with the
  prompt-to-file install steps, and its copy test asserts the new guidance.
- Lifecycle: exact endpoints, ADMIN-only rendering, typed revoke confirmation,
  rotate shows the token once and clears it on close, re-enroll polls
  `credential_version` (not `RE_ENROLLED`).
- Applications: VIEWER has no deployment controls; REVOKED copy is correct.
  `applications.test.tsx` currently mocks `useAdmin` only and has no VIEWER or
  REVOKED case; both are added in the same slice.
- Guidance: `HOST_REVOKED`, `BOOTSTRAP_TOKEN_ACTIVE`, network, and unknown codes
  render correct actions; no secret appears in the DOM after closing a dialog.
- `npm run build` (tsc + Vite) and the full Vitest suite.
- Test rewrites are owned by the slice that changes the behavior, never deferred:
  slice 1 keeps `StatusBadge` green with the widened union; slice 3 removes the
  `api.login`/`Authorization: Bearer` assertions from `docker.host.test.tsx`
  (that test mocks `/operators/login` and then asserts a bearer header — both
  go) and updates `enrollment.test.tsx` unregister fixtures (no duplicate-host
  case exists there today; the wizard adds one); slice 4 rewrites
  `enrollment.test.tsx` onboarding assertions and `servers.test.tsx`
  (simulation add/remove and the inline login test become wizard tests);
  slice 5 updates lifecycle assertions; slice 6 updates `console.test.tsx`
  (simulated navigation tests become real-host navigation tests) and the
  dashboard; slice 7 deletes `simRegistry.test.ts` and rewrites the remaining
  simulation assertions in `auth.test.tsx` and `console.test.tsx`
  (`environment.test.tsx` and `views.test.tsx` use real fixtures or mocked data
  and should already pass).

**Committed harness (optional gate)**

Add `frontend/scripts/e2e-onboarding.mjs` (Playwright) that starts a temp-DB API
and Vite, drives ADMIN and VIEWER contexts, and asserts: revoked ≠ offline; wizard
issues a real token; VIEWER has no actions; dialogs are keyboard-operable. It is
documented as a local/optional gate because Playwright is not a current dependency
and adding a browser job to CI is a separate infrastructure decision. If approved,
add an `e2e` job to `ci.yml` with explicit browser install, timeout, and artifact
upload. Do not claim it runs in CI until it does.

**Data compatibility check**

- Copy the demo DB, run startup migration on the copy, verify operators, hosts,
  telemetry, and operation counts are unchanged and host identities stable. The
  live DB remains untouched and read-only.
- Verify `HostOut` reads against the copied legacy DB (no `agent_mode` column until
  migration, `null` afterward).

**Manual/unverified (reported, not claimed)**

- Actual systemd install, remote agent restart, multi-host Linux behavior, Azure
  onboarding, and Docker execution remain unverified and unauthorized.

## Delivery slices (reviewable commits)

Each slice keeps `pytest`, `npm test`, `tsc -b`, and `vite build` green on its own.

1. `feat(backend): effective host status, agent mode, and lifecycle guards` —
   D1/D2/D3, host events endpoint, environment patch + audit, migration and
   active-token index, tests, `docs/API.md`. Includes the minimal frontend
   contract guard (widen `HostStatus`, add the `StatusBadge` defensive fallback
   and its test) so no commit can render a crashing badge.
2. `feat(agent): one-shot re-enroll and credential-file application` — D6 flags
   with exit codes, identity backup/restore, tests, `NIMBUSOPS_AGENT_ACTION`
   wrapper support.
3. `feat(frontend): design primitives, code-aware errors, cookie-only auth` —
   tokens, `ui/`, `ApiFailure.code`, readiness 503 handling, remove the legacy
   bearer path and its test setup.
4. `feat(frontend): zero-friction enrollment wizard` — D2 derivation, command
   templates, wait/expiry/`BOOTSTRAP_TOKEN_ACTIVE` recovery, tests.
5. `feat(frontend): host lifecycle, history, and service panels` — D4/D6 dialogs,
   runtime panel, events history, tests.
6. `feat(frontend): unified dashboard, settings, and status consumers` — dashboard,
   Settings control-plane panel, Applications/Sidebar/ServerList/HostDetail
   corrections.
7. `feat(frontend): remove simulated registry and finalize verification` — delete
   the sim source and its test, rewrite remaining simulation assertions, optional
   E2E harness, sprint acceptance doc.

Each slice is a single reviewable commit on `sprint/ux-perfection`; the design doc
and the implementation plan are committed before slice 1. Slices 1–2 are backend
and agent only (the UI contract guard in slice 1 is the one frontend touch, so
the widened status can never crash the interim UI); slices 3–7 are frontend and
each depends only on already-merged slices.

No push, merge, deploy, or live-service change without separate approval.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Status literal widening affects a client | Add `connectivity`, document the change, keep live-host values identical |
| StatusBadge crashes on a new value | Fallback ships in the same commit as the widening (truth rule 1) |
| Token leaks via command/history/DOM/logs | Prompt-to-file entry, no interpolation, one-time memory-only panel, clear on close |
| Re-enroll replaces a credential by accident | Explicit `--reenroll`, token required, identity backup, restore on failure, server intent check |
| Re-enroll leaves the service down after a "successful" repair | One-shot verifies a heartbeat with the new credential before exiting 0; UI keeps polling `last_seen_at` |
| Rotation missed grace window | Countdown + hard warning; next-step copy; re-enroll is the documented recovery |
| Older agents report no mode | `null` → explicit "not reported"; never guess executor capability |
| Multiple active tokens | Server-side one-active guard with explicit revoke-and-reissue |
| Polling storm or overlapping requests | Single `useFleet`/`useOnboarding` poll, in-flight guard, pause when hidden |
| Revoked host looks recoverable by retry | No retry path; only re-enroll; banner explains that the server rejects the credential with 401 `HOST_REVOKED` |
| Legacy DB blocks startup on index creation | Fail-safe skip with warning, matching the in-flight-operation pattern |
| Removing simulation breaks a demo script | Intended honesty change; demo scripts must use real hosts or be updated |
| Destructive action misfire | Typed confirmation, ADMIN, consequences list, no optimistic UI |
| E2E harness rots | Committed script + docs; required gates remain CI pytest/Vitest/tsc/build |

## Explicit non-goals

- Remote installation, remote restart, or browser-driven service control.
- New enrollment protocol for fresh hosts, multi-tenant roles, or user management.
- Schema rewrites, data resets, or changes to existing host identities.
- Light theme, theming, or a component-library migration.
- Deployment to live infrastructure or modification of running services.
- CI browser job unless separately approved (the harness is committed first).
