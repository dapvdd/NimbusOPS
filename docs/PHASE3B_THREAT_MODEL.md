# Phase 3B Threat Model — Secure Real-Host Enrollment

**Status:** DESIGN — NOT IMPLEMENTED.
**Date:** 2026-11-10 · Branch: `feat/phase3b-secure-enrollment`

---

## 1. Scope and Assumptions

**In scope:** Phase 3B enrollment, operator authentication, host credential lifecycle, Docker authorization, and the cross-host isolation between Phase 3A simulated hosts and real infrastructure.

**Assumptions stated as "not verified in app code; verify at runtime/edge":**
- Transport security (TLS/cert verification) is the operator's deployment responsibility, not the app's. Evidence: `client.py` uses `httpx.Client` with default TLS verification; `docs/SECURITY.md` documents the operator's responsibility.
- Network access controls (firewall, VPN, Tailscale ACLs) restrict who can reach the server. Evidence: `applications.py:1-6` documents trusted-local model.
- Operator workstation is not compromised.

---

## 2. Threat Actors

| Actor | Capability | Intent |
|---|---|---|
| **Network neighbor** | Can reach server HTTP endpoint | Deploy infrastructure mutations without authorization |
| **Malicious/untrusted operator** | Knows enrollment token, has browser access | Enroll unauthorized hosts, revoke legitimate hosts, pivot between hosts |
| **Compromised host** | Controls agent process, owns credential | Exfiltrate telemetry, access another host's operations |
| **Compromised operator workstation** | Browser session | Trigger mutations as the operator |
| **Replay/MITM attacker** | Network-level interception | Replay enrollment tokens, impersonate agents |

---

## 3. Risk Assessment (Findings from Code Audit)

### 3.1 Critical

**[C1] Unauthenticated operator mutations — infrastructure-wide**

All application endpoints (`/applications/deploy`, `/{id}/start`, `/{id}/stop`) accept requests without any operator authentication. Any client with HTTP access to the server can:
- Deploy Nginx containers to any enrolled host.
- Start/stop containers on any enrolled host.
- Trigger operations on DavidLab (confirmed enrolled in local DB).

**Evidence:** `applications.py:65-80` — zero `Depends` guards. `test_unauthed_mutation_rejected` (test_deployments.py:312-318) explicitly documents this as accepted Phase 2 behavior.

**PRD requirement:** AC-01 (operator auth before mutations) is a Phase 1 acceptance criterion. This has been deferred past Phase 2 without mitigation.

**Impact:** Critical. A network neighbor can deploy arbitrary Nginx containers across all enrolled hosts.

**Phase 3B mitigation:** All application endpoints require operator session. Existing hosts retain their credentials. New enrollments require bootstrap tokens.

---

**[C2] Re-enrollment silently un-revokes hosts**

The existing enrollment flow (`hosts.py:77-103`) resets `is_revoked=False` on re-enrollment with the same hostname. Anyone who knows the shared static `NIMBUSOPS_ENROLLMENT_TOKEN` can re-enroll a revoked host and obtain a fresh credential, bypassing revocation.

**Evidence:** `hosts.py:91-93` — `existing.is_revoked = False; existing.revoked_at = None`. No operator action required.

**Impact:** Critical. Revocation is non-final; an operator cannot trust a revocation.

**Phase 3B mitigation:** Re-enrollment requires an operator-issued bootstrap token (not the enrollment token). Revocation is permanent until explicitly reversed by an operator with auth.

---

**[C3] Bootstrap token grants full infrastructure access**

The current static enrollment token grants both enrollment AND subsequent agent access to the server. An attacker who obtains it can:
- Enroll arbitrary hosts under arbitrary hostnames.
- Rotate credentials of existing hosts.
- Gain agent-level access to telemetry and command operations.

**Evidence:** `security.py:44-49` — enrollment token is the bootstrap credential; it has no expiry, no rate limit, and can be reused indefinitely.

**Impact:** Critical. Token disclosure = full compromise of the control plane.

**Phase 3B mitigation:** Split credential into (a) bootstrap token (short-lived, single-use, grants enrollment only) and (b) per-host agent credential (long-lived, grants telemetry + commands only). Bootstrap tokens are issued by the operator and scoped to hostname.

---

### 3.2 Important

**[I1] No operator authentication**

No login, session, or API key for operator actions. Browser and server share no authentication boundary.

**Evidence:** `applications.py` — no `Depends` anywhere. `agents.py` — no operator auth for any endpoint.

**Impact:** Important. Anyone who can reach the HTTP endpoint can mutate infrastructure (see C1).

**Phase 3B mitigation:** Operator session (cookie + CSRF token or Bearer token). All application endpoints guard on operator auth. AC-01 becomes satisfiable.

---

**[I2] Host identity not cryptographically bound**

`X-Host-Id` header is client-supplied and validated only against the stored token. A compromised host with valid credentials can change its `X-Host-Id` to another host's ID and send telemetry for that host, or claim operations for that host (backend prevents result submission but poll response is delivered first).

**Evidence:** `agents.py:57-58, 76-77` — `X-Host-Id` taken from header, `authenticate_host` uses it as a lookup key. No cryptographic binding.

**Impact:** Important. With compromised credentials, a host can send telemetry under another host's ID, causing data integrity issues.

**Phase 3B mitigation:** Agent credential is bound to the `host_id` (server-generated UUID). The agent cannot know another host's UUID without it being disclosed. The `X-Host-Id` header is trusted only because it comes from the agent that holds the corresponding credential — the credential IS the identity proof. This is standard bearer-token semantics. The existing `FORBIDDEN_HOST` check on result submission (C3 in Phase 2 test suite) protects operations. The threat is credential-theft from a compromised host.

---

**[I3] Credential rotation requires re-enrollment**

The only way to rotate a host's credential today is re-enrollment (same hostname → new token, stable UUID). This cannot be done without knowing the existing hostname.

**Evidence:** `hosts.py:88-103`.

**Impact:** Important. An operator cannot rotate a credential without re-enrolling — there is no separate rotation endpoint. Revocation without rotation wastes the hostname.

**Phase 3B mitigation:** New `POST /api/v1/hosts/{id}/rotate-credential` (operator-authenticated). Generates new credential, optionally expires old one after grace period.

---

**[I4] No operational timeout for stuck RUNNING operations**

Operations claimed by an agent stay RUNNING indefinitely if the agent dies without reporting. No claim-timeout exists.

**Evidence:** `deployments.py:230-273` — poll atomically claims QUEUED→RUNNING; no time limit on RUNNING state. PRD FR-15 acknowledges this.

**Impact:** Important. A dead agent leaves operations stuck; the operator sees RUNNING forever.

**Phase 3B mitigation:** Implement claim timeout (configurable, default 10 minutes). After timeout, operation is re-queued. Add `claimed_at` and check in `poll_commands`.

---

**[I5] Revocation check bypassed on re-enrollment**

Confirmed in C2 above — re-enrollment resets `is_revoked`. This also means an operator cannot reliably revoke a host: the adversary simply re-enrolls.

**Phase 3B mitigation:** Part of C2 fix. Re-enrollment requires bootstrap token. Bootstrap tokens are operator-issued and can be audited.

---

### 3.3 Minor

**[M1] Agent token pepper uses enrollment token as default**

If `NIMBUSOPS_TOKEN_PEPPER` is unset, the enrollment token is used as the pepper in the keyed hash. When the enrollment token is rotated or disclosed, all existing agent token hashes become weaker.

**Evidence:** `security.py:33-34` — `pepper = settings.token_pepper or settings.enrollment_token`.

**Phase 3B mitigation:** Mandate `NIMBUSOPS_TOKEN_PEPPER`. Bootstrap tokens are separate from the pepper mechanism.

---

**[M2] Agent identity file is world-readable on Windows**

`os.chmod(path, 0o600)` is best-effort, silently skipped on Windows (`config.py:75`). Any Windows user process can read the plaintext agent credential.

**Evidence:** `config.py:69-75`.

**Phase 3B mitigation:** Document the limitation. For Windows deployments, consider using DPAPI (Windows Data Protection API) via `python -m win32crypt` or equivalent to encrypt the stored credential at rest. Not implemented in Phase 3B.

---

**[M3] No rate limiting on enrollment**

`/agents/enroll` has no rate limit. An attacker with the enrollment token can spam enrollment attempts. Each attempt is audited but not throttled.

**Evidence:** `agents.py:31-45` — no `Depends(rate_limit)` guard.

**Phase 3B mitigation:** Add rate limiting to enrollment endpoint (30 attempts/minute per IP). Bootstrap tokens add an additional layer: they expire and are consumed, limiting the blast radius of a leaked bootstrap token.

---

**[M4] Enrollment audit log can be gapped**

`enrollment_audit` table has no unique constraint on (hostname, outcome) — multiple entries for the same hostname are possible (confirmed in DB: `david-lab` has 2 DENIED entries before ENROLLED). No tamper protection.

**Evidence:** Inspected DB; `models/__init__.py:66-76`.

**Phase 3B mitigation:** `host_events` append-only table with event type, actor, timestamp. For Phase 3B, the audit log is for visibility, not legal non-repudiation.

---

**[M5] Docker ownership validation is agent-side only**

Container name prefix (`nimbusops-`) check is enforced in `docker_exec.py` before Docker is touched. Backend does not verify container ownership in the `container_state` response — a compromised agent could report false state.

**Evidence:** `agent/nimbusops_agent/docker_exec.py:172-173`.

**Impact:** Minor (agent is trusted in Phase 2 trust model). In Phase 3B with multiple hosts, a compromised agent could report fake state for another host's containers.

**Phase 3B mitigation:** Agent-side enforcement remains (defense-in-depth). Backend could add independent Docker state verification in a future phase (out of scope for Phase 3B).

---

## 4. Threat-Mitigation Matrix

| Threat | Phase 1-2 Status | Phase 3B Mitigation | Residual Risk |
|---|---|---|---|
| C1: Unauthenticated mutations | Accepted limitation | Operator auth on all app endpoints | Operator credential theft |
| C2: Re-enrollment un-revokes hosts | Not mitigated | Bootstrap token required; revocation final | Bootstrap token theft |
| C3: Bootstrap token = infra access | Full access with enrollment token | Split: bootstrap grants enrollment only | Operator insider |
| I1: No operator auth | No mitigation | Session/Bearer token | Auth scheme implementation |
| I2: Host identity not crypto-bound | Standard bearer token | Credential IS identity proof | Credential theft from host |
| I3: No credential rotation | Re-enrollment only | Dedicated rotation endpoint | Grace period overlap |
| I4: Stuck RUNNING ops | No timeout | Configurable claim timeout | Agent network partition |
| I5: Revocation bypassable | Not mitigated | Bootstrap token required for re-enroll | Bootstrap token theft |
| M1: Pepper = enrollment token | Not mitigated | Mandate `NIMBUSOPS_TOKEN_PEPPER` | Token disclosure |
| M2: World-readable identity file | Best-effort chmod | Document; DPAPI future work | Windows local privilege |
| M3: No enrollment rate limit | No mitigation | Rate limit enrollment endpoint | Brute-force bootstrap token |
| M4: Audit log gap | No unique constraint | `host_events` append-only table | Tampering post-breach |
| M5: Agent-reported Docker state | Agent-side enforcement | Agent-side enforcement remains | Compromised agent |

---

## 5. Phase 3B Security Properties (What Can and Cannot Be Claimed)

### Can be claimed after Phase 3B implementation:
- Operator mutations require authenticated operator session.
- Enrollment requires an operator-issued, short-lived, single-use bootstrap token.
- Agent credentials are independently revocable without re-enrollment.
- Revocation is permanent until explicitly reversed by an operator.
- Host identity is bound to the server-generated UUID and its corresponding bearer credential.
- Simulated `sim-` identifiers are rejected at the backend before any data access.
- Docker operations are blocked by default on newly enrolled hosts.
- Concurrent enrollment with the same hostname is handled atomically (no duplicate hosts).
- Concurrent enrollment with different hostnames does not interfere.
- Agent restart with a revoked credential stops the agent loop.
- Audit events are recorded for enrollment, revocation, and rotation.

### Cannot be claimed without additional measures:
- TLS transport security (requires deployment-time configuration).
- Agent credential confidentiality on Windows (world-readable identity file).
- Prevention of credential theft from a compromised agent host.
- Prevention of a compromised operator workstation from triggering mutations.
- Legal non-repudiation of audit records (append-only enforced in-app, not at DB level).
- Docker container ownership verification independent of agent-reported state.
- Rate limiting on application mutation endpoints (requires operator auth first; then rate-limit by session).
- Prevention of Tailscale/VPN-based network access (network layer, not app layer).

---

## 6. Testing Requirements by Threat

| Threat | Test Type | Test Description |
|---|---|---|
| C1 | Negative | Unauthenticated POST /applications/deploy → 401 |
| C2 | Negative | Revoke host → re-enroll with same hostname (no bootstrap) → 401 |
| C3 | Bootstrap flow | Bootstrap token consumed after use; cannot enroll a second time |
| I1 | Negative | No session/Bearer → POST /applications/deploy → 401 |
| I3 | Positive | Rotate credential → old token invalid after grace → 401 |
| I4 | Positive | Agent claims op → process killed → op re-queued after timeout |
| I5 | Negative | Revoke host → heartbeat → 401 |
| M3 | Negative | 31 enrollment attempts in 1 min → 429 |
| Concurrency | Concurrency | Two concurrent enrollments with same hostname → exactly one succeeds |
| Sim isolation | Negative | Fetch with `X-Host-Id: sim-xxx` → 400 |
