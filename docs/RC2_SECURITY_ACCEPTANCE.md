# RC2 Security Acceptance

- Candidate: `rc2/hardening` @ `b3fb6a7`
- Scope: the RC1 audit's security-relevant defects (F01/F04/F05/F06/F07/F08/
  F14/F15) plus the trust-model controls they touch.
- This is an **internal, source-and-test-based acceptance**, not an independent
  penetration test or a production security certification.

## Control results

| Control | Verdict | Evidence | Notes |
|---|---|---|---|
| Enrollment trust root is unambiguous | PASS | `test_rc2_enrollment_contract.py::test_conflicting_enrollment_credentials_rejected` | Exactly one credential; both → 400 `ENROLLMENT_MODE_CONFLICT` |
| Secure profile can disable the shared secret | PASS | `::test_bootstrap_mode_disables_legacy_shared_token`, `::test_bootstrap_mode_still_allows_bootstrap_enrollment` | `NIMBUSOPS_ENROLLMENT_MODE=bootstrap` |
| Shared secret cannot take over an existing host | PASS | `::test_legacy_reenroll_does_not_replace_existing_credential` + heartbeat with the original credential still 200 | F08 closed; re-enrollment is operator-bootstrap only |
| Bootstrap token is single-use, scoped, hashed | PASS | existing `test_bootstrap_enrollment.py` + F07 atomicity test | Consumption and host creation share one transaction; a failed enrollment does not burn the token |
| Agent credential is never logged or persisted in plaintext server-side | PASS (unchanged RC1 property re-checked) | `core/security.py` keyed hash; no token material in operation/event payloads (`test_operation_history.py` sanitization pin) | Not re-audited beyond these pins |
| Authorization: mutations require operator + role | PASS (unchanged) | `test_docker_authz.py`, `test_host_lifecycle.py` | RC2 added no new mutation bypass |
| Docker disablement blocks all mutation paths | PASS | `test_rc2_docker_safety.py`, `test_worker.py` | Dispatch + execution, both required to fail for a mutation to run |
| Docker mutations require proven ownership | PASS (mocked Engine only) | `agent/tests/test_rc2_docker_safety.py` (13) | **Runtime Engine verification is BLOCKED**; see runtime acceptance |
| Container success is evidence-based | PASS (mocked Engine only) | same file, F06 cases | Inspection failure is UNKNOWN, never fabricated success |
| Operation results cannot be overwritten or raced | PASS | `test_rc2_transactions.py` (stale fence, one winner, concurrent deploy) | CAS + partial unique index |
| Agent identity file is confidential and atomic | PASS (runtime, this host) | `test_config.py` atomicity tests; `icacls` shows one ACE for the current user, inheritance removed; POSIX 0600 test skipped on Windows | Windows ACL path exercised with real `icacls` |
| Health does not hide a degraded dependency | PASS | `test_rc2_health.py` | Liveness vs readiness split |
| Dependency vulnerability state | **PARTIAL** | `npm audit`: 8 advisories — 5 moderate, 1 high, 2 critical | See below |

## Dependency advisory review (`frontend`, `npm audit`)

| Package | Severity | Direct | Fix available | Assessment |
|---|---|---|---|---|
| `vitest`, `tinypool` | critical | vitest yes | 5.1.0 (major) | Test-only tooling; not in the production bundle |
| `vite` | high | yes | 8.3.8 (major) | Build tool; not shipped at runtime, but a compromised build toolchain is still a supply-chain risk |
| `react-router`, `react-router-dom` | moderate | dom yes | 7.18.5 (major) | **Runtime dependency**; fixing requires a v6→v7 migration |
| `esbuild`, `vite-node`, `@vitest/mocker` | moderate | no | transitive | Tooling |

**Decision.** Do not force major upgrades inside a defect-closure candidate;
doing so would replace a tested security fix with an untested framework
migration. These remain open with an explicit follow-up: plan a dedicated
toolchain/upgrade change (react-router 7, vite 8, vitest 5) with its own
regression and build verification. Until then RC2's honest position is
"known vulnerable dev toolchain; one moderate runtime advisory accepted
temporarily".

## Incident closure (G7) — BLOCKED

The RC1 audit requires an owner decision on whether historically exposed
credential material was ever valid for, or reused against, a live system. RC2
hardened the *mechanism* (no silent rotation, atomic identity, no argv secret),
but **cannot close the historical incident**:

- No authorization was given to inspect production credential stores, rotate
  production secrets, or contact the incident owner.
- No evidence was fabricated or inferred; the question remains open.

Required to close: incident-owner statement on exposure window and reuse,
confirmation that any credential that could have been exposed is revoked, and a
recorded rotation for still-active hosts.

## Non-claims (explicit)

- No TLS/ingress, firewall, Tailscale ACL, or public-reachability verification
  was performed (G8 remains UNVERIFIED).
- No independent penetration test, fuzzing campaign, or SAST tool was run.
- No production system was touched; all verification used the local worktree,
  local SQLite, and fake Docker CLI.
- Docker runtime isolation, non-root execution, and Engine-level protections are
  **not** verified here.

## Security verdict

All RC1 *code-level* security defects in scope are closed or have a named
residual. The release is **not** security-accepted for production: ownership
enforcement and disablement still need real-Engine proof (G5), the historical
incident is unresolved (G7), and ingress isolation is unverified (G8).
