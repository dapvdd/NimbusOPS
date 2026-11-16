# Deployment examples (inert)

These are reviewed, parameterized patterns adapted from the RC2 demo
deployment (`demo/multihost-rc2` @ `f931003`, `deploy/demo-multihost`). They
are examples only: nothing here is installed, enabled, or validated on Linux
by NimbusOps in this change. Replace every `@TOKEN@` before use.

## Why these and not the originals

Deliberately not imported from the demo tree:

- fixed Tailscale/public addresses, ports (`18220`/`18221`), service account
  names, `/opt/...` paths, demo hostnames, and demo databases;
- the HOLD-gated `phase2-provision.sh` provisioning flow and
  `provision_helpers.py` (they assume demo users, paths, and database);
- `build_release.py` and the pinned Caddy archive digest (demo release lane).

Kept: the security shape — loopback API, separate web listener, unprivileged
service accounts, `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`,
empty capability sets, a token file instead of argv, an identity file that is
never replaced silently, and a telemetry-only unit that cannot see Docker.

## Substitutions

| Token | Meaning |
|---|---|
| `@INSTALL_DIR@` | Install root, outside home directories |
| `@VENV_DIR@` | Python environment containing backend + agent |
| `@CONFIG_DIR@` | Root-owned configuration directory |
| `@STATE_DIR@` | Absolute state directory owned by the service account |
| `@STATE_DIR_NAME@` | `StateDirectory=` name (resolves under `/var/lib`) |
| `@SERVICE_USER@` / `@SERVICE_GROUP@` | Dedicated unprivileged account |
| `@DOCKER_GROUP@` | Docker-capable group, executor unit only |
| `@API_BIND_ADDRESS@` / `@API_PORT@` | API listener (loopback) |
| `@CONTROL_PLANE_URL@` | Agent's control-plane base URL |
| `@CONTROL_PLANE_ALLOW@` | Exact address/CIDR for agent egress |
| `@CADDY_BIN@` | Caddy binary path |
| `@SCHEME@`, `@PUBLIC_HOST@`, `@PUBLIC_PORT@`, `@PUBLIC_BIND_ADDRESS@` | Public web listener |
| `@AUTO_HTTPS@` | `on` for DNS names with TLS, `off` only for private/loopback |
| `@FRONTEND_DIST@` / `@API_UPSTREAM@` | Built SPA directory / API upstream |
| `@UI_ORIGIN@` | Exact browser origin, e.g. `https://ops.example.internal` |
| `@GENERATE_UNIQUE_RANDOM_SECRET@` | 32+ random bytes, hex or base64 |

## Invariants

- **Secrets never ride in argv.** Use `--bootstrap-token-file`; the token file
  must be mode `0600`, owned by the agent account, and not a symlink.
- **One identity per host.** Do not copy `agent.json` between hosts. If the
  file already exists, the enrollment wrapper refuses to replace it; use the
  console's re-enroll flow only after explicit approval.
- **Choose one mode per host.** Do not run the telemetry-only and executor
  units against the same state file.
- **Telemetry-only is behavior control plus unit sandbox**, not a complete
  security boundary. The OS account, filesystem, and host policy must agree.
- **`NIMBUSOPS_SESSION_COOKIE_SECURE=true` needs HTTPS.** Set it to `false`
  only for an explicitly loopback HTTP preview.
- **Origins are exact.** Never use `*`; `NIMBUSOPS_BROWSER_ORIGINS` gates
  cookie-authenticated mutations and must match the UI origin.
- **Keep `backend.env` at mode `0600`** and back up the SQLite database before
  upgrades. No schema migration is required by the auth feature.

## Verification status

These files have not been installed or exercised on a Linux host in this
session. Treat service startup, sandbox behavior, and multi-host enrollment as
unverified until an approved infrastructure test records evidence.
