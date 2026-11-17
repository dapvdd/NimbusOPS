# ADR-5.1 — Windows persistence: pinned WinSW 2.x service wrapper

- Status: ACCEPTED (design decision, 2026-11-17; conditional Sprint 5 approval)
- Context: Sprint 5 requires reboot-persistent Windows startup for the NimbusOps agent. Native Windows SCM wrappers must be idempotently installable, support graceful stop and upgrades, run without user login, and be redistributable under a license the project can ship. Task Scheduler was rejected: it is job-based, weaker at service supervision, restart/backoff and crash recovery semantics. A native service installer was rejected for this sprint's packaging scope.
- Decision:
  - Use WinSW **2.x stable** as the SCM wrapper: pinned release `WinSW-x64.exe` **v2.12.0** from `https://github.com/winsw/winsw/releases`, MIT licensed.
  - Wrapper renamed to a NimbusOps-specific binary name (`nimbusops-agent-service.exe`) with `nimbusops-agent-service.xml`; never a generic shared name.
  - Service start mode automatic (delayed autostart configurable); `<onfailure>` recovery actions with bounded restart backoff; `<stoparguments>`/`stoptimeout` for graceful SIGTERM-equivalent stop of the Python daemon.
  - Pinned runtime: 64-bit Python (see ADR-5.5 matrix) invoked by absolute path; no PATH reliance, no PowerShell execution-policy bypass.
- Provenance requirements (mandatory before packaging):
  - Record in the release manifest: exact version tag, direct download URL, SHA-256 of the exact downloaded binary, MIT license text reference, and retrieval date. The build/install tooling MUST verify the digest before first use; a mismatch aborts installation with a typed error.
  - Verify the binary is authentic: check the Authenticode signature where present; cross-check the digest against a second retrieval (NuGet `WinSW 2.x` package or GitHub release assets) recorded in the manifest.
  -npm `winsw` wrapper package is NOT used (third-party npm packaging, unpinned provenance).
- Consequences:
  - WinSW 2.x maintenance state is quiet upstream; the pinned digest freezes behavior regardless. Wrapper upgrade is a deliberate manifest change requiring re-verification.
  - WinSW runs the daemon under the configured service account; account selection, ACL hardening and virtual-account compatibility are governed by the design (§8) and verified on disposable Windows hosts (G6/G7) before real acceptance.
  - If signature verification or digest cross-check cannot be completed in the target environment, the Windows adapter reports SETUP_REQUIRED; it does not fall back to Task Scheduler or an unpinned binary.
- Enforcement: D6W tests assert manifest digest verification runs before install; missing/mismatched digest is a typed SETUP_REQUIRED/ARTIFACT_UNAVAILABLE failure, never a silent install.
- Note: the exact WinSW 2.x release tag and digest are recorded at packaging time (G6); 2.12.0 is the pinned target as of this ADR and must be re-confirmed against the live GitHub releases/NuGet listing during D6W packaging, since the version above was selected from search evidence, not a direct release-page fetch.
