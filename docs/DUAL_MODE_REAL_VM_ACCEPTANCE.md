# Real-VM acceptance — blocked at HTTPS prerequisite

Candidate: `bf08140b6b71d58fcbda1691978be75137c7153a`.
Execution date: 2026-11-20. No installation, snapshot restore, production access,
push or merge performed. Latest sudo verification and cleanup below supersede
the historical privileged-access blocker.

## TLS trust remediation — 2026-11-21

Local remediation supersedes the static trust-contract blocker below, not the
live acceptance results. See `docs/TLS_TRUST_CONTRACT.md` for configuration.

- Explicit target CA policy/manual wizard input reaches curl and the installer
  across sudo as arguments, then enrollment and generated systemd ExecStart.
- Custom HTTPX trust uses an explicit verifying SSL context. Default HTTPX
  behavior remains unchanged. No system/certifi store is modified.
- Root-controlled CA paths are validated and a root-owned 0644 persisted copy
  is readable through a 0755 directory. Private keys are rejected.
- New artifact: `nimbusops-agent-1.0.0rc2-dualmode2-ubuntu24.04-amd64.tar.gz`.
  SHA-256: `cf2bced62d522473af86dd623458835711957dec25d8ab8c0aac501616a3f2c1`.
  Both generators pin it; a regression checks archived source equality and the
  unchanged old artifact digest. Frozen WSL runtime/artifact were not replaced.
- Independent read-only review found restrictive-umask directory readability,
  missing UI input, and pending release pins; these were addressed. Permission
  tests execute real filesystem operations under umask 077, with ownership
  identity modeled for an unprivileged sandbox, not an actual service account.
- Final `PYTHONPATH=agent;. python -m pytest -q`: **515 passed, 11 skipped**,
  3 dependency deprecation warnings, Windows Python 3.13. Ten POSIX-only tests
  skipped there passed separately using WSL Python 3.12: **10 passed**, 1 warning.
  The remaining historical skip persists. Frontend Vitest: **162 passed / 26
  files**; `npm run build`: TypeScript and Vite passed.
- A loopback-only ephemeral TLS test verifies private trust succeeds and
  wrong-host/untrusted connections fail; this is not VM network-path evidence.
  Test credentials are generated in temporary test storage, not shipped.

Remaining limitations: no full installer sandbox execution, real sudo sanitization,
service-account read or real systemd startup was exercised. Command propagation
and unit wiring have static contract tests; persistence has executable POSIX
tests. Source CA paths must remain protected from concurrent privileged changes.
Legacy Docker-executor wizard custom trust is explicitly unsupported/disabled;
the dual-mode verified telemetry installer is the supported path. Dependency
advisories and unrelated previously documented issues were not remediated here.

**Ready for renewed isolated real-VM acceptance preparation**, not deployment.
Privileged guest work remains unauthorized; no guest certificates, grants,
listeners or snapshots changed. Automatic Setup and Manual Bootstrap remain
**NOT RUN / BLOCKED** pending separately authorized live execution and snapshot
confirmation. Katrina rehearsal remains unperformed; deployment is **NO-GO**.

## Private-CA investigation after HTTPS authorization (historical)

The operator authorized private isolated HTTPS and temporary guest CA trust,
but explicitly did not renew temporary passwordless sudo. Investigation used
read-only pinned SSH; no certificates, trust changes, listener, installer,
service override, or worker dispatch were created in this phase.

- [x] Reverified WSL candidate HEAD and immutable archive digest against the
  values above. Inspected `install.sh`, bundled HTTPX 0.28.1 `_config.py`,
  bundled certifi 2026.1.4 `core.py`, and bundled agent client directly from
  the SHA-256-pinned archive, not just repository source.
- [x] Reverified expected guest machine ID/hostname over pinned SSH, absence
  of `/etc/sudoers.d/nimbusops-acceptance`, and absence of an agent identity.
  Both `sudo -n id -u` and `sudo -n bash -c 'id -u'` were denied with
  `sudo: a password is required`. The read-only check exited 0.
- [x] Trust boundary identified: generated manual command and worker download
  use curl with HTTPS verification enabled. With a suitable system trust
  installation, this download path can use a private CA; it was not live-tested.
  Worker dispatch is `sudo -n bash -c ...` and has no explicit CA forwarding.
- [x] Agent client calls `httpx.Client(timeout=timeout)`. The pinned HTTPX
  implementation uses `SSL_CERT_FILE` or `SSL_CERT_DIR` if present, otherwise
  explicitly loads `certifi.where()`. The pinned certifi implementation
  resolves its packaged `cacert.pem`, not the Ubuntu system CA bundle.
- [x] Installer invokes enrollment through `runuser` without an explicit CA
  setting and writes a systemd unit without `Environment=SSL_CERT_FILE=...`
  or an environment file. Installing a CA into guest OS trust alone therefore
  does not configure the bundled agent's default certifi trust store. A shell
  export alone also does not configure the generated persistent service.
- [ ] End-to-end private-CA support: BLOCKED for the unchanged generated path.
  A scoped enrollment environment plus a service override could retain full
  certificate/hostname verification, but this is additional trust plumbing
  requiring explicit review/authorization; it was not silently introduced.
  No certifi bundle patch, TLS bypass, global service-manager environment,
  sudo-policy change, or installer/artifact modification was performed.
- [ ] Installation remains independently blocked by absent privileged access.
  HTTPS authorization does not authorize recreating the removed sudo grant.
- [ ] Live TLS validation, install, service status, fresh heartbeat/telemetry,
  and Manual Bootstrap single-use checks remain NOT RUN. Static artifact
  inspection is not evidence of a successful TLS connection.

Evidence: mode-0600
`/home/david/nimbusops-acceptance-data/ca-contract-check.json` records artifact
trust implementation and the fresh guest checks. No new regression suite was
run and no application code changed. No temporary TLS resources were created,
so none require cleanup from this phase. Snapshot restoration remains subject
to separate confirmation. Deployment remains **NO-GO**, including the separate
unperformed Katrina migration rehearsal.

## Historical SUDO_READY execution

- [x] Pinned SSH matched the expected machine ID, hostname and fingerprint.
- [x] Effective `(root) NOPASSWD: ALL` rule and noninteractive root shell verified.
  Initial `visudo -c` failed because the root:root drop-in was mode 0640. After
  checking the exact authorized rule and rejecting symlinks, changed only this
  dedicated file to 0440. Full `visudo -c` then passed; root UID was 0.
- [x] Candidate preflight passed: Ubuntu 24.04 amd64, expected machine binding,
  existing agent identity absent.
- [x] WSL HEAD remains the exact candidate; Git status is clean.
- [x] Health/OpenAPI returned 200; health database status was ok. Unauthenticated
  `/api/v1/provisioning/targets` returned 401.
- [x] Local immutable agent archive SHA-256 matches
  `8f0a715761aff04920201409c95d648450329d68acb1e41a616c5e131637d7d9`.
- [x] Actual SSH using a separate empty known-hosts file rejected the connection
  with exit 255 and host-key verification failure; verification was not disabled.
- [ ] Trusted VM-reachable HTTPS origin: BLOCKED. Existing API listens only on
  WSL `127.0.0.1:18080`; no HTTPS listener, Caddy, nginx or cloudflared was found,
  and no provisioning origin is configured in the existing API environment.
  No public tunnel or guest CA trust change was made without authorization.
- [ ] Automatic install, worker, systemd and fresh heartbeat/telemetry: NOT RUN.
- [ ] Snapshot restore and Manual Bootstrap/single-use checks: NOT RUN.
- [x] Mandatory privilege cleanup: removed only the dedicated acceptance
  drop-in through the verified guest channel, confirmed absence, ran full
  `visudo -c` successfully, invalidated sudo timestamp, and verified both
  noninteractive root command and root shell now require a password. Cleanup
  script exited 0. No passwordless acceptance grant remains.

Evidence outside Git: `/home/david/nimbusops-acceptance-data/` contains
`pre-dispatch-checks.json` and `sudo-cleanup.json`. No new regression-suite run
is claimed. The earlier 33-test result below remains historical evidence.

**Acceptance remains BLOCKED; deployment remains NO-GO.** Next security decision
is approval of a private isolated HTTPS endpoint and temporary private-CA trust
on this disposable guest, or provision of an already trusted isolated origin.
Snapshot restoration still requires separate explicit confirmation. Katrina,
DavidLab production and Azure were not accessed or modified.

## Results

| Gate | Result | Observed evidence |
| --- | --- | --- |
| WSL candidate | PASS | Ubuntu-24.04 WSL2, user david, exact candidate HEAD; clean WSL Git status |
| API process | PASS | PID 1518, cwd `/home/david/projects/nimbusops-acceptance`, `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 18080` |
| API health/routes | PASS | `/api/v1/health` 200, database ok, NimbusOps version 1.0.0-rc2; `/api/openapi.json` 200 |
| Isolated database | PASS (existing runtime) | `/home/david/nimbusops-acceptance-data/acceptance.db`, read-only SQLite quick_check ok; provisioning schema present |
| SSH trust/target | PASS | Strict pinned SSH succeeds; fingerprint and machine ID match the supplied values; hostname ubuntuserver, Ubuntu 24.04.5 LTS x86_64 |
| Credential-file permissions | PASS | Identity, target policy and known_hosts each mode 0600 |
| Noninteractive sudo | BLOCKED | `sudo -n -l`: password required; candidate preflight raises SSH_PREFLIGHT_REJECTED |
| Automatic Setup | BLOCKED | No dispatch or installation attempted after sudo rejection |
| Agent/systemd/heartbeat/telemetry | BLOCKED | Not installed or verified in this execution |
| HTTPS origin and worker | NOT RUN | Privileged-access blocker reached before starting new runtime components |
| Clean snapshot restore | NOT RUN | No destructive action taken; identity verified, restore authorization still required before execution |
| Manual Bootstrap/single-use live test | BLOCKED | Baseline restore and privileged installation not executed |
| WSL focused regressions | PASS | 33 passed, 1 dependency warning; exit 0 |
| Katrina backup/migration rehearsal | NOT RUN | Outside this VM run; deployment remains NO-GO |

## Diagnosis

The reported root-level 404 responses do not indicate backend failure. The
candidate defines health at `/api/v1/health` and OpenAPI at
`/api/openapi.json`. Both actual endpoints responded correctly. Runtime
environment points at the supplied isolated database and SSH policy. The current
process sends startup output to `/dev/pts/0`; historical startup logs were not
retrieved and no durable startup-log evidence is claimed.

The existing Automatic Setup implementation uses `sudo -n test` in preflight
and `sudo -n bash -c <fixed-generated-installer>` for installation. Current sudo
authority cannot run it unattended. No password was requested or captured, no
password prompt was bypassed, and no new sudo grant was installed.

## Regression evidence

Executed in the WSL candidate virtualenv:

```text
python -m pytest -q backend/tests/test_provisioning_api.py
  backend/tests/test_provisioning_jobs.py
  backend/tests/test_onboarding_reliability.py
  backend/tests/test_local_acceptance.py backend/tests/test_migration.py
33 passed, 1 warning in 7.68s
```

Includes independent-process confirmation/enrollment and Linux local-lock
regressions, not live installation or crash/stress acceptance. Captured output:
`/home/david/nimbusops-acceptance-data/regression-result.json` (outside Git).

## Required decision / verdict

The operator explicitly approved temporary passwordless root-shell sudo for
`ubuntuserver` on this disposable VM only, using a dedicated visudo-validated
drop-in, with removal and verification of noninteractive denial after acceptance.
Snapshot restoration still requires separate explicit confirmation.

Post-approval read-only verification confirmed:

- Windows and WSL repositories remain at the exact candidate commit.
- Strict pinned SSH again matched the supplied fingerprint, machine ID,
  hostname and Ubuntu 24.04.5 LTS x86_64.
- VirtualBox VM `Ubuntu_Server`, UUID
  `5ffbf7c9-616b-4476-83f9-ae577a32bb47`, is running. Its three NIC MACs match
  those read over SSH; host-only MAC `08:00:27:8a:96:d6` carries
  `192.168.56.107` in the guest.
- The same VM has current snapshot `NIMBUSOPS-CLEAN-BASELINE`, UUID
  `4c8141af-86a1-4d29-a69a-db4cd2518321`. Snapshot existence and binding are
  verified; clean guest contents are not yet proven by a restore/test.
- `/usr/sbin/visudo` exists in the guest, but `sudo -n true` still requires
  authentication. The existing acceptance SSH identity cannot log in as root
  (`Permission denied (publickey,password)`); no password was attempted.

The remaining blocker is **privileged access, not approval**. No authenticated
guest-root channel is available to install the approved drop-in. An operator
must perform the one-time authenticated guest sudo bootstrap. No sudo policy,
VM state, installer, WSL policy or production environment was changed. No
additional tests or live acceptance passes are claimed by this recheck.

**Real-VM acceptance: BLOCKED. Deployment: NO-GO.** Separate Katrina verified
backup/copy migration rehearsal is still mandatory even after both VM modes pass.

## Operator bootstrap validation follow-up

After the operator reported saving the drop-in, independent pinned SSH checks
again matched the expected guest identity and fingerprint. The effective file
`/etc/sudoers.d/nimbusops-acceptance` is root:root, mode 0640, and **zero bytes**.
The directory also contains `nimbusops-acceptance.tmp` (38 bytes, root:root,
0700) and `.nimbusops-acceptance.tmp.swp` (1024 bytes). These artifacts suggest
an unfinished editor transaction; their contents were not readable through the
unprivileged account and no active editor files were modified.

`sudo -n -l`, `sudo -n /usr/bin/id -u`, and `sudo -n /bin/bash -c 'id -u'`
each report that a password is required. The attempted privileged `visudo -c`
cannot run, so policy syntax validation is BLOCKED, not passed. The effective
drop-in currently grants no access; the operator must finish saving and exiting
the authenticated visudo session. No installation or snapshot action occurred.
