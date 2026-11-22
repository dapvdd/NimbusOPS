# Full MVP M2/M5 — monitoring and disposable recovery evidence

## Authorized telemetry repair addendum

After the initial evidence collection, repair authorization expanded to the telemetry handler and this worker's new test module. Two test-first cases (aware/naive timestamps one year ahead) failed with HTTP 200 instead of expected 422 before the fix. The telemetry handler now interprets naive time as UTC, normalizes offset-aware time to UTC, and rejects `recorded_at` more than five minutes ahead of server receipt with the established 422 `detail` validation shape, after authenticating and before persistence/liveness mutation. Delayed samples and duplicate retries remain accepted; no migration, sequence protocol, or enrollment behavior changed. Server receipt time already controls `last_seen_at` in the service. Eight focused cases passed after repair, including old samples, modest future skew, offset normalization, and rejection without connectivity refresh. This limits new future poisoning; it does not repair existing poisoned rows or change past-sample freshness semantics. Broad verification results are supplied in the follow-up worker report.

Coordinator reports that the final immutable `fullmvp2` artifact/source equality gate passes; the earlier archive failures (`dualmode2`, then `fullmvp1` after a later client fix) are historical evidence, not assertions about the final artifact. Caddy changes remain coordinator-owned.

Follow-up targeted command: `python -m pytest backend/tests/test_full_mvp_monitoring.py backend/tests/test_hosts_telemetry.py backend/tests/test_agent_auth.py backend/tests/test_utc_wire_timestamps.py backend/tests/test_bootstrap_enrollment.py backend/tests/test_tls_release.py -q` → **42 passed, 1 warning**, exit 0 (6.06 s), independently confirming the current artifact equality gate. New-file Ruff/Black/strict Mypy pass; `git diff --check` exits 0 with line-ending warnings. Whole-file Ruff for `agents.py` still reports five pre-existing B008 (`Depends` defaults) and one existing RUF100 (unused `BLE001` noqa); unrelated handler/style code was not altered.

Date: 2026-11-22. Scope: independent local validation in `integration/full-mvp-rc`, Windows, Python 3.13.7. This is **not Ubuntu, systemd, Docker, network TLS, or production acceptance**. No remote infrastructure, package installation, privileged operation, historical database, or protected archive was used or modified. No commit was made by this worker.

## Outcome

- Monitoring, enrollment replay rejection, authorization, migrations and local recovery checks pass in the selected suite: **186 passed, 10 skipped** (38.13 s, exit 0).
- New isolated evidence tests: **3 passed**, including API connectivity transitions/recovery, duplicate telemetry characterization/retention, and SQLite online backup/restore with identity/telemetry preservation and repeated migrations.
- **Historical release gate failures were resolved locally:** the original `dualmode2` divergence and the later `fullmvp1` divergence (after a client acknowledgement fix) were reproduced; a final immutable `fullmvp2` artifact was built from the reviewed wheel/current source and both pins were updated. The equality gate now passes; real-host execution of that artifact remains an unmet acceptance gate.
- Ten CA persistence permission tests are skipped on Windows. Live Ubuntu and deployment acceptance remain mandatory.

## Reproducible commands and results

From the repository root, using existing Python/tools only:

```powershell
python -m pytest backend/tests/test_full_mvp_monitoring.py backend/tests/test_enrollment.py backend/tests/test_bootstrap_enrollment.py backend/tests/test_agent_auth.py backend/tests/test_hosts_telemetry.py backend/tests/test_effective_status.py backend/tests/test_revocation_revision.py backend/tests/test_rc2_enrollment_contract.py backend/tests/test_migration.py backend/tests/test_wal_mode.py backend/tests/test_browser_auth.py backend/tests/test_operator_auth.py backend/tests/test_cors.py backend/tests/test_security_headers.py backend/tests/test_login_rate_limit.py backend/tests/test_installer_tls.py backend/tests/test_ca_persistence.py backend/tests/test_utc_wire_timestamps.py backend/tests/test_bootstrap_intent.py backend/tests/test_rc2_transactions.py backend/tests/provisioning/test_schema_migration.py -q -rs
```

Result: **186 passed, 10 skipped, 1 warning**, exit 0. Skips: `test_ca_persistence.py:17` (1), `:38` (3), `:55` (6), all `POSIX installer permissions`. Warning: Starlette TestClient's deprecated AnyIO `BlockingPortal` alias. No test was weakened or disabled.

```powershell
python -m pytest backend/tests/test_tls_release.py -q
```

Result: **1 failed**, exit 1, reproducible independently. Failure at `backend/tests/test_tls_release.py:20`, archive member/source equality. Read-only enumeration identified `docker_exec.py`, `main.py`, `worker.py` as differing members in `nimbusops-agent-1.0.0rc2-dualmode2-ubuntu24.04-amd64.tar.gz`. The archive SHA and both pins pass the earlier assertions. Other workers were concurrently modifying agent recovery; the coordinator must rerun this gate after integration, not erase the finding or rewrite an immutable archive in place.

Earlier targeted monitoring/migration baseline: **57 passed, 1 warning** (5.93 s, exit 0). An intermediate expanded selection including the release test returned **1 failed, 63 passed, 10 skipped** (17.47 s, exit 1). These overlap the consolidated selection; do not sum counts.

Final focused test/static commands:

```powershell
python -m pytest backend/tests/test_full_mvp_monitoring.py -q
python -m ruff check backend/tests/test_full_mvp_monitoring.py
python -m black --check backend/tests/test_full_mvp_monitoring.py
python -m mypy --strict backend/tests/test_full_mvp_monitoring.py --follow-imports=silent
```

Final focused rerun: **3 passed, 1 warning**, exit 0; Ruff, Black check and strict Mypy each exit 0. Mypy checks the new module only, with imported implementation checks suppressed; this is not a repository-wide type-check claim. Initial Black check reported formatting differences; only the owned new file was adjusted.

## Coverage and limits

| Criterion | Evidence | Limit |
|---|---|---|
| Enrollment and identity | Existing enrollment/bootstrap/intent/transaction tests: valid enrollment, one-use token consumption, same-token replay `409 BOOTSTRAP_TOKEN_CONSUMED`, scope/expiry/revocation, secure mode and conflicting credential rejection | TestClient and synthetic fixture identities, not remote installer acceptance |
| Heartbeat/telemetry authentication | Missing/wrong/foreign identity credentials rejected; valid heartbeat succeeds; revocation tests pass | Does not demonstrate live host reconnect or packet confidentiality |
| Metrics persistence/history | Existing telemetry tests cover latest/history ordering, null-before-first-sample, input bounds, and public token non-disclosure | No long-running throughput/load claim |
| Connectivity truth | New read-API test: never-seen OFFLINE → heartbeat ONLINE → aged row STALE → aged row OFFLINE → heartbeat ONLINE; existing effective-status unit tests ensure REVOKED wins | Ages disposable database timestamps; does not wait through real wall-clock intervals or restart systemd |
| Telemetry retry semantics | New characterization submits identical telemetry three times: all HTTP 200, bounded to two rows with fixture retention limit | Telemetry is **not replay/dedup protected**. Do not confuse bootstrap replay rejection with sample replay rejection |
| Fresh/legacy migration | Existing Phase3B and Sprint5 schema tests, synthetic legacy preservation and idempotency pass | No historical/live database opened; legacy test's docstring overstates token-auth coverage—the synthetic legacy test does not call authenticate |
| Online backup/restore | New test uses SQLite backup API from fixture WAL database to backup then separate restore; full logical dump equality, integrity/FK checks, two Phase3B+Sprint5 reruns, restored host credential authentication and telemetry CPU value | In-process SQLite/SQLAlchemy check, not process restart, power-loss, concurrent-write stress, encrypted backup or remote retention validation |
| Browser/API access controls | Existing cookie/CSRF/origin, operator role/session, CORS, header and login-rate-limit tests pass | Narrow code/config review, not a full dependency or application security audit |
| TLS installer contract | Static installer assertions pass: custom CA prepared before package mutation, persisted/readability checks, CA passed to enrollment and service | Ten POSIX permission tests skipped; no TLS handshake or running deployment checked |

## Security/release findings

### M5-01 — Historical source/archive divergence (locally resolved)

**Location:** `backend/tests/test_tls_release.py:9–22`; original `dualmode2` archive above. **Historical evidence:** checksum/pin assertions passed while source-member comparison failed for three agent modules. **Local disposition:** coordinator created `fullmvp1`, then superseded it with `fullmvp2` after the final client acknowledgement fix; both were built from reviewed wheel bytes/current source, pins were updated, and the final equality gate PASSED. Old immutable archives were not modified. **Remaining gate:** the final artifact has not executed on an authorized fresh Ubuntu host, so this is not real-host acceptance. No evidence established credential disclosure or malicious tampering.

### M5-02 — Medium deployment configuration gap: TLS example is not self-sufficient

**Location:** `deploy/examples/Caddyfile.example:4–8`; `deploy/examples/README.md:39`. The example substitutes `auto_https @AUTO_HTTPS@`, while README recommends `on` for DNS TLS. Caddy's documented `auto_https` option is not an `on/off` boolean; default automatic HTTPS is ordinarily enabled by omitting the option. The template also has no explicit certificate/key stanza for private-PKI HTTPS while recommending `off` for private listeners. **Impact:** copying substitutions verbatim can produce a rejected or nonfunctional TLS configuration. **Disposition:** runtime `caddy validate` on the intended rendered config is a deployment gate; review exact Caddy version and choose explicit certificate configuration or default automatic HTTPS. Caddy is not invoked here; this is a static configuration finding, not a reproduced installed-host failure. Do not expose a private/tailnet listener over HTTP merely to make it start.

Reference checked read-only on 2026-11-22: [Caddy global options: auto_https](https://caddyserver.com/docs/caddyfile/options#auto-https), whose accepted modes are `off`, `disable_redirects`, `ignore_loaded_certs`, `disable_certs`; `off` disables automation, not the HTTPS protocol.

### M2-01 — Telemetry trust contract (future skew fixed, retries characterized)

**Location:** `backend/app/services/hosts.py` and `backend/app/api/agents.py`. Each accepted telemetry payload inserts a row, refreshes `last_seen_at` with server receipt time, and stores client `recorded_at`; latest metrics still sort by client timestamp. Duplicate retries are accepted and bounded by retention: this is a deliberate characterization, not bootstrap replay protection. Gross future timestamps are now rejected with 422 before persistence or liveness refresh (five-minute skew allowance). Old samples remain valid and cannot move receipt-based liveness backward. This is not an unauthenticated auth bypass; TLS and token ownership remain the trust boundary. Existing poisoned rows are not retroactively repaired.

No Critical exploitable defect was demonstrated within this narrow review. That is not a general security assurance.

## Reviewed deployment invariants (configuration only)

- `deploy/examples/backend.env.example:5–11`: bootstrap-only enrollment, required unique pepper placeholder, exact browser/CORS origins, secure session cookies enabled; secret file mode 0600 documented. Keep pepper stable with restored state; changing it can invalidate credentials/CSRF. Backup restoration requires separately protected configuration/identity recovery, not just the DB.
- `backend/app/api/operators.py:34–59,136–166,216–238`: signed CSRF token, exact allowed-origin check when supplied, hashed expiring/revocable operator sessions, cookie mutation checks, role gate, HttpOnly/SameSite Strict/Secure browser session cookie. Origin absence still requires valid CSRF; no wildcard default is accepted by app CORS construction (`main.py:68–70`).
- `deploy/examples/systemd/nimbusops-api.service.example:10–24`: dedicated account, one worker, 0700 state/0077 umask, no capabilities, NoNewPrivileges and filesystem restrictions. API bind address is a placeholder; README requires loopback. Enforce that in rendered configuration, not by assumption.
- Telemetry unit has no Docker group and makes Docker/sudo paths inaccessible (`nimbusops-agent-telemetry.service.example:13–33`); actual supplementary groups, kernel sandbox support and filesystem permissions remain unverified.
- `agent/nimbusops_agent/client.py:54–58`: HTTPX verifies normal HTTPS trust by default, or uses a custom CA context; no verification disable was found in that construction. HTTP URLs are still transport choices; never render a remote production control-plane URL as HTTP.
- Login limiter is in-memory and process-local (`operators.py:73–86`); the one-worker unit matches that limitation, but restarts reset the window. No distributed-rate-limit claim.

## Minimal real Ubuntu authorization plan — NOT EXECUTED

Request one consolidated, time-bounded authorization from the infrastructure owner, naming fresh disposable Ubuntu 24.04 host(s), exact IP/DNS/ports, allowed SSH account, dedicated service accounts/paths, new isolated DB/state directories, artifact digest/version, trust root/certificates, and any package/service/root changes. Explicitly exclude all historical hosts, databases, jobs, identity files, protected artifacts and snapshots. Require owner-approved teardown scope. This worker has not requested or exercised credentials.

1. **Preflight before mutation:** approve artifact/provenance and new immutable pins; validate rendered Caddy/systemd configuration using installed tools; verify TLS chain and hostname from browser/agent trust contexts. Never use insecure TLS flags. Record version/digests and redacted configuration.
2. **Fresh isolated deployment:** owner authorizes required packages, accounts, service installation/start, firewall ports and Docker separately. Keep backend loopback-only, unprivileged API, exact HTTPS UI origin, secure cookies and dedicated secret files. Run POSIX CA permission tests including symlink/ownership/readability failures before enrolling.
3. **Monitoring acceptance:** issue one-use hostname-scoped bootstrap token via authenticated admin UI/API; enroll a fresh unique host using token file, verify replay/foreign-host rejection without exposing token material, observe repeated real heartbeat/telemetry in UI, then intentionally stop/start only the new agent service and observe real ONLINE→STALE→OFFLINE→ONLINE transitions. Verify state identity remains stable and revoked credentials fail closed.
4. **Backup/upgrade/restore:** use SQLite online backup or an owner-approved stopped-service backup (never copy only a live WAL main file), store protected config/pepper/identity separately; restore into another fresh authorized path with no outbound jobs, run integrity/FK checks and migrations twice, start an isolated backend on a distinct loopback port and compare row identities/metrics plus authenticated access. Never overwrite source/live DB or restore a historical snapshot.
5. **Recovery and sandbox gates:** coordinator owns agent operation recovery/Docker acceptance; use only newly approved images/containers/resources and require explicit permission for service restart, network interruption and Docker operations. Test telemetry-only OS account cannot reach Docker. No historical job retry or broad cleanup.
6. **Evidence and teardown:** capture exit status/timestamps, redacted service logs, TLS verification result, identity continuity, migration/schema markers and backup integrity; clean only enumerated disposable resources after owner approval. Any skipped/failed gate keeps MVP deployment BLOCKED.
