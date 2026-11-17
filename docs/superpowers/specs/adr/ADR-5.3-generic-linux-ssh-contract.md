# ADR-5.3 — GENERIC_LINUX: SSH transport and least-privilege installation contract

- Status: ACCEPTED (design decision, 2026-11-17)
- Context: Design §6 requires a pre-established authorized channel with pinned host identity for GENERIC_LINUX; the operator approved SSH with strict host-key verification and least-privilege installation.
- Decision:
  - **Transport:** OpenSSH client from the worker host (server-side), key-based only (Ed25519 dedicated key per connection), `StrictHostKeyChecking=yes`, host key pinned in server connection config (key file reference, not DB plaintext). No password auth, no agent forwarding, no X11, no `ProxyJump` beyond pinned config.
  - **Remote account:** dedicated non-root management account (e.g. `nimbusops-mgmt`) with a fixed `sudoers` fragment permitting exactly the pinned manager executable and the pinned installer path (`NOPASSWD`), configured once by the operator during connection setup. No `sudo sh`, no wildcards, no general root shell.
  - **Command shape:** every SSH invocation runs the fixed root-owned manager binary (`/usr/local/sbin/nimbusops-manager`) with a JSON request on stdin (§15.4 framing) and reads the framed response from stdout. No user-controlled argv fragments; target labels never interpolate into shell strings. Remote stderr is captured but never returned raw to the dashboard.
  - **Manager/installer privilege:** the manager runs as root via the pinned sudo rule; the NimbusOps daemon runs as the dedicated unprivileged telemetry account; state dir `/var/lib/nimbusops-agent` 0700 owned by the daemon account; manager journal/lock at `/var/lib/nimbusops-agent/manager` per §15.3.
  - **Framing/interruption:** SSH disconnect mid-action leaves the manager journal as source of truth (write-ahead + fsync before effect, per §5); reconnect STATUS reconciles. `ServerAliveInterval` bounded; connect/read timeouts per design §5 defaults.
  - **First-install bootstrap:** the pinned installer script is transferred over the authenticated SSH channel itself (stdin → temp file → digest verify → root-owned install) — no inbound network listener is required on the target at any point. The bootstrap transfer is itself journaled and digest-verified before execution.
- Consequences:
  - Connection setup (account, sudoers, host key pinning, key distribution) is operator work during provider connection configuration; missing pieces surface as SETUP_REQUIRED with exact remediation steps, never auto-remediated.
  - Host key change or manager digest mismatch blocks the connection (fail closed) until re-validated.
  - Real acceptance requires a disposable Ubuntu host with reboot (G7); protocol logic is mock-tested earlier.
- Enforcement: D6L tests cover request framing, digest verification, journal dedup, disconnect reconciliation; D0 freezes wire fixtures.
