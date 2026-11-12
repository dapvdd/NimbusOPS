# NimbusOps Phase 6 — Security Review

Date: 2026-11-12 · Branch: `feat/autonomous-phase4-6` · Scope: v1 release candidate

## 1. Method

- Endpoint-by-endpoint auth matrix review against the accepted Phase 3B threat
  model (trusted-local reads, authenticated mutations).
- Targeted adversarial tests added this phase: rate limiting, security headers,
  Bearer-prefix enforcement, IDOR/ordering pins on history, injection pins on
  agent argv.
- Dependency audit (npm audit, pip outdated) and secrets-handling review.

## 2. Authentication & authorization matrix (as implemented)

| Endpoint group | Auth | Evidence |
| --- | --- | --- |
| `GET /api/v1/hosts*`, metrics, inventory, templates, applications, operations, events | Public read (trusted-local threat model) | Design decision recorded in PHASE3B docs; unchanged. |
| `POST /applications/*`, lifecycle ops | ADMIN session + docker_enabled gate | test_restart_op, test_phase2_flow |
| Host PATCH / rotate / revoke / bootstrap issue | ADMIN session | test_host_lifecycle |
| Agent heartbeat/telemetry/poll/result | Per-host agent token (hashed, grace window) | test_agent_auth |
| Operator login | Rate limited, no enumeration | test_login_rate_limit (4) |
| Operator logout/me | Session bearer | test_operator_auth |

Findings: **no unauthorized mutation path found**. All mutations resolve an
operator or agent credential server-side; role checks are in the dependency,
not the handler body (cannot be forgotten per-route).

## 3. Hardening delivered this phase

1. **Login rate limiting** — per-username sliding window (5/300 s default,
   env-tunable), 429 `RATE_LIMITED`, fail-closed (correct password also
   rejected while limited), success resets. Limit applies before credential
   work ⇒ unknown usernames are throttled too. Limitation: in-memory state is
   per-process; multi-worker deployments need shared state (documented).
2. **Security headers** — middleware sets `X-Content-Type-Options: nosniff`,
   `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, tight CSP on every
   response including 404s and /api/docs.
3. **Bearer strictness** — Authorization without the `Bearer ` scheme is now
   401 (was: accepted raw token). Oversized/garbage tokens → 401.
4. **SQLite WAL** — `PRAGMA journal_mode=WAL` on connect: bounds writer/reader
   contention; busy_timeout 5000 retained.
5. **Injection pins (agent)** — container names flow as single fixed-argv
   elements through `subprocess` (no shell); hostile names (`;`, `$()`,
   backticks, `--privileged`) either fail the managed-prefix gate or arrive
   as one opaque argument — proven by tests, not by review alone.

## 4. Token & credential hygiene

- Agent tokens: 256-bit random, stored as keyed SHA-256; plaintext shown once;
  rotation with bounded dual-accept grace; revocation immediate.
- Bootstrap tokens: single-use (atomic redemption ⇒ exactly-one-success under
  32-way race), TTL ≤ 1 h, hostname-scoped, stored hashed.
- Operator passwords: PBKDF2-SHA256 240k iters; generic invalid-credentials
  message (no user enumeration).
- Logs: no token/password material (pinned by grep review + existing tests);
  identity file on agent is 0600.
- Frontend: session token in memory only (never localStorage/cookies).

## 5. Dependency review (recorded 2026-11-12)

**npm (8 advisories: 2 critical, 1 high, 5 moderate):**
- tinypool ≤2.1.1 critical (RCE gadget) — **dev-only** (vitest worker pool);
  not present in production `dist/` or runtime deps. Fix: vitest 5 (breaking).
- esbuild ≤0.24.2 moderate (dev-server request forgery) — dev-only; not
  applicable to served production assets.
- vite ≤6.4.3, vitest ≤4.1.10, vite-node, @vitest/mocker — dev chain, same.
- react-router 6.30 moderate (open redirect via backslash in `<Link>`; SSR
  `deserializeErrors` injection). Runtime dependency; SPA uses fixed internal
  paths and no SSR — pattern not reachable. Fix: react-router-dom 7 (breaking).

Decision: no silent breaking upgrades in the release window. Tracked as
accepted risks with upgrade actions in NIMBUSOPS_V1_RELEASE_CANDIDATE.md.

**Python:** no pip-audit available in venv; `pip list --outdated` shows drift
(fastapi 0.115.14 → 0.162, starlette 0.46 → 1.x, sqlalchemy 2.0.43 → 2.1)
with no known CVEs cited against the pinned versions; python-multipart 0.0.20
is past the CVE-2024-53981 fix. Upgrades are a scheduled maintenance task, not
a release blocker.

## 6. Secrets review

- `.env` git-ignored (verified via `git check-ignore`).
- No `.db`/credential files tracked in git (verified via `git ls-files`).
- Test code uses synthetic tokens only; no real credentials in repo.
- `NIMBUSOPS_TOKEN_PEPPER` documented as rotate-with-re-enrollment.

## 7. IDOR / privilege escalation probes

- Operation events for unknown ids → 404 `OPERATION_NOT_FOUND` (no info leak
  via timing differences beyond normal lookups).
- Cross-host isolation: ops carry host_id from the deployment record, never
  from client input beyond the target deployment; restart/dispatch on host A
  cannot act on host B (pinned by Phase 3B isolation tests + FR-09 filtering).
- Simulated host ids (`sim-*`) rejected server-side at every agent endpoint
  and at enrollment.

## 8. Residual risks (explicit, accepted for v1)

| # | Risk | Mitigation | Severity |
| --- | --- | --- | --- |
| R1 | Public reads (trusted-local model) | Deploy behind network boundary; operator-authenticated reads deferred | Medium |
| R2 | In-memory rate limiter is per-process | Run single worker; or move to shared store in v1.1 | Low |
| R3 | Dev-chain npm advisories | Upgrade vitest/vite/react-router majors post-release | Low (prod impact: none found) |
| R4 | No TLS termination built in | Terminate TLS at reverse proxy; agent supports https URLs | Medium (ops) |
| R5 | Legacy shared-token path exists | Leave `NIMBUSOPS_ENROLLMENT_TOKEN` empty in production | Low |

## 9. Verdict

**No Critical or Important findings remain open in the shipped code.** The
release candidate may proceed to controlled deployment behind a network
boundary with the residual risks above tracked.
