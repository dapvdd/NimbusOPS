# Emergency single-host demo — 2026-11-20

## Status and scope

Candidate only: **NO-GO for claiming a verified Ubuntu dashboard-first demo**
until a disposable Ubuntu 24.04 amd64 installation and browser flow pass.
No production deployment, Azure change or tunnel modification is authorized or
performed. Existing production ADMIN/VIEWER behavior is not changed remotely.

Implemented: explicit dashboard hostname in agent Config/CLI/environment,
private-token telemetry installer, deterministic distribution with offline pinned
Python wheels, checksum-first dashboard command, and explicit Add Server
confirmation for a revoked host. The legacy host-detail reenroll dialog and
executor install path remain separate and are not this demo's accepted path.

## Release

Artifact: `frontend/public/releases/nimbusops-agent-1.0.0rc2-dualmode1-ubuntu24.04-amd64.tar.gz`.
The frontend production build copies this to `dist/releases/`; serving this exact
path is a deployment gate, not an assumption that production already has it.

SHA-256: `8f0a715761aff04920201409c95d648450329d68acb1e41a616c5e131637d7d9`.

The bundle contains Python agent source, `install.sh`, a hash-locked dependency
list and Linux amd64 wheels. Python packages install with `--no-index` and
`--require-hashes`. Ubuntu apt packages (Python, venv, CA certificates) still
require working configured apt repositories. No repository checkout or shared
enrollment token is required on the target. No Docker access is granted.

Rebuild from the checkout:

```powershell
python -m pip download --dest deploy/releases/wheels --platform manylinux2014_x86_64 --python-version 312 --implementation cp --abi cp312 --only-binary=:all: httpx==0.28.1 psutil==6.1.1 anyio==4.8.0 certifi==2026.1.4 httpcore==1.0.9 idna==3.10 h11==0.16.0 sniffio==1.3.1 typing_extensions==4.12.2
python deploy/build_agent_release.py --wheels deploy/releases/wheels --output deploy/releases/nimbusops-agent-1.0.0rc2-dualmode1-ubuntu24.04-amd64.tar.gz
```

Compare the printed digest with the reviewed hash before copying it into
`frontend/public/releases/`. Any agent or installer change requires a new
immutable release name and digest; never silently overwrite a published release.

## Operator-assisted Azure steps — only after separate approval

1. Select one Ubuntu **24.04 amd64** host with sudo and outbound HTTPS to the
   approved control plane and Ubuntu apt repositories. No inbound agent port is
   required. Do not change Azure networking or expose API ports for the demo.
2. Validate time synchronization and TLS certificate trust. Keep the public
   dashboard hostname; do not use HTTP or disable certificate checks.
3. ADMIN: Add Server → enter the exact chosen FQDN → Telemetry only → Generate
   enrollment token. Generate shortly before use (default expiry 10 minutes).
4. Copy the verified installation command from the Install step. The command
   downloads the pinned bundle and checks SHA-256 **before extraction**. Run it
   in an interactive SSH terminal on the approved host.
5. Paste the token only at the hidden installer prompt. Never paste it into a
   command, ticket, chat, environment argument or shell history. The installer
   writes a transient 0600 token file and removes it on normal exit/failure.
6. Verify service locally:
   `sudo systemctl status nimbusops-agent --no-pager` and
   `sudo journalctl -u nimbusops-agent -n 50 --no-pager`.
   Do not copy credential files into logs or the presentation.
7. Dashboard Verify must bind to the consumed token's host ID and show ONLINE
   with heartbeat, telemetry and metric timestamps after enrollment and within
   90 seconds. Observe at least three reporting cycles. Service startup alone
   does not establish acceptance. Check VIEWER can read the host but cannot issue
   tokens or mutate credentials.
8. For Remove → Re-add: record host ID, remove through authenticated dashboard,
   confirm the old credential is rejected, then Add Server with the same FQDN.
   Click **Confirm re-enroll**, copy the new token and command containing
   `--reenroll`, then verify the same host ID and fresh telemetry. Do not perform
   concurrent lifecycle actions during the demo.

### Clearly labeled fallback (not a completed wizard)

If release hosting is unavailable, transfer the reviewed bundle by the approved
operator channel. Verify its SHA-256 locally before extracting, then invoke:

```bash
sudo bash install.sh https://APPROVED-CONTROL-PLANE exact-dashboard-hostname
```

This uses the same private prompt and installer; it is **not clean-Ubuntu-tested
in this session**. The tested fallback is the local developer-OS real-agent HTTP
integration test, not proof that this shell installer works on Ubuntu. Do not
represent either as a live Azure demonstration until observed on that host.

## Production deployment plan — not executed

1. Obtain separate approval naming target, candidate SHA and rollback owner.
2. Validate candidate in disposable Ubuntu with a scratch control plane and
   disposable ADMIN/VIEWER credentials. Run the complete browser-to-installer
   path, restart recovery and stable-ID re-add before promotion.
3. Review deployed backend compatibility and migration requirements relative to
   production (this candidate adds no database migration itself). Back up the
   database and preserve current deployed artifacts and configuration. Do not
   assume code rollback reverses checkpoint migrations.
4. Build frontend from the exact reviewed SHA. Stage its hashed assets and
   `/releases/<immutable artifact>` together using the existing deployment
   procedure. Verify downloadable bytes match the reviewed SHA-256; HTML SPA
   fallback at the archive URL is a failure.
5. Deploy only the approved component/revision using existing release procedure,
   preserving origin, TLS, tunnel, auth, CSRF and VIEWER configuration. Smoke-test
   ADMIN and VIEWER before enrolling the demo host.
6. On regression, stop promotion and restore prior compatible application
   artifacts using the approved recovery procedure; verify public dashboard and
   both logins. Do not alter database state blindly.

## Remaining acceptance blockers

- No Linux distribution in WSL and no Docker executable available locally;
  clean Ubuntu installer/systemd execution and browser E2E not performed.
- No live Azure telemetry or production artifact reachability observed.
- Concurrent revoke revision increment/admission fencing and ownership checks at
  consumption remain unverified; **full lifecycle acceptance is prohibited**.
- Active token lookup uses a bounded list and hostname matching for reenroll;
  exact-ID response/lookup is deferred. Concurrent administrative lifecycle
  operations are not supported by this demo acceptance.
- Legacy executor commands still require a repository checkout; only telemetry
  mode receives the new distribution.
- Existing dependency vulnerabilities/lint findings from the prior checkpoint
  are not remediated by this sprint.

## Evidence and review ledger

- Final `python -m pytest -q`: 459 passed, 1 skipped, 3 deprecation warnings.
- `npm test -- --reporter=dot`: 146 passed across 24 files, React Router warnings.
- `npm run build`: TypeScript and Vite passed; release copied into `dist/releases`.
- `python -m pytest backend/tests_integration/test_agent_backend.py backend/tests/test_demo_agent_path.py -q`:
  4 passed, 3 deprecation warnings. Real loopback HTTP bootstrap/FQDN/collectors
  reached ONLINE; isolated ASGI Remove/Re-add preserved host ID. This is Windows
  developer-host telemetry, not Ubuntu/Azure telemetry or browser E2E.
- Git Bash `bash -n deploy/agent-install.sh`: passed.
- Git Bash `sha256sum --check --status`: final original accepted, appended
  corruption rejected. This does not execute apt or systemd.
- Final rebuild produced the same reviewed SHA-256.
- `python -m mypy --strict deploy/build_agent_release.py`: passed (one file only).
- `python -m black --check deploy/build_agent_release.py`: formatting check failed;
  deferred, not a correctness acceptance claim. Whole-agent strict typing not run.
- Independent read-only review found runtime access permissions and service
  recovery after registration/first-telemetry failure. Both changed after a
  failing safety-contract test; those tests are static contracts, not OS-level
  execution proof.
- Deferred minor: installer rejects one-character hostnames; choose a conventional
  multi-character FQDN for this demo. No change to hostname scope on the server.
- Ruling: use existing Python agent and telemetry-only service rather than a new
  executable/runtime — shortest path; cost is Ubuntu Python/venv apt prerequisites.
- Ruling: no clean Ubuntu environment available; stop short of live-install claims
  rather than installing WSL or modifying Azure without authorization.
- Ruling: preserve identity after registration when the first telemetry cycle
  fails, and let systemd retry; cost is that startup is not ONLINE proof.
- Ruling: leave pagination, legacy executor/host-detail flow and concurrent
  lifecycle fencing out of this candidate; cost is incomplete lifecycle acceptance.
