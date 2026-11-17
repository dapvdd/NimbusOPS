# ADR-5.5 — Supported OS and artifact compatibility matrix

- Status: ACCEPTED (design decision, 2026-11-17; certification requires G6/G7 real-host acceptance)
- Context: The design requires an explicit support matrix; the operator approved "supported Ubuntu LTS and Windows x64 targets".

## Matrix (initial sprint scope)

| Component | Version / constraint | Source of truth |
|---|---|---|
| Ubuntu agent (GENERIC_LINUX, AZURE_VM Linux) | Ubuntu 24.04 LTS x86_64 (24.04.x point releases allowed; ARM64 out of scope) | systemd unit + manager acceptance tests |
| Windows agent (LOCAL_WINDOWS, AZURE_VM Windows) | Windows Server 2022 x64; Windows Server 2025 x64 accepted by same codepath but certified only if tested (G7) | WinSW wrapper + manager acceptance tests |
| Python runtime (agent, both OS) | CPython 3.12.x pinned in release manifest (matches Azure preparation's 3.12 baseline; exact patch pinned by digest) | release manifest |
| WinSW wrapper | WinSW-x64 2.12.0, digest-pinned (ADR-5.1) | release manifest |
| Azure SDK | official `azure-identity`, `azure-mgmt-compute` pinned versions (exact pins recorded in backend dependency manifest during implementation) | backend dependency manifest |
| Azure Run Command API | 2023-03-01 or later (treatFailureAsDeploymentFailure) | adapter manifest |
| Control plane (worker/API) | same host as baseline server; SQLite WAL local disk per design §1 | baseline constraints |

- Out of scope this sprint: ARM64 anywhere, other distros (Debian/RHEL/Alma), Ubuntu 20.04/22.04, scale sets, sovereign clouds, macOS, containers-as-targets.
- Every provisioning job records `artifact_digest` + `config_hash` from the release manifest; validation refuses unsupported OS/arch with UNSUPPORTED_OS (422).
- The matrix is data (versioned server configuration), not scattered code: adapters read the matrix; changing supported versions is a reviewed config change with its own validation evidence, not a code edit.

## Release artifact rules
- One immutable release artifact per agent version per OS: pinned digest, manifest-recorded; installers refuse digest mismatch (typed ARTIFACT_UNAVAILABLE).
- Trusted distribution: control-plane-hosted allowlisted HTTPS location (or operator-supplied location recorded in connection config); no arbitrary public internet fetch at install time beyond the allowlisted URL recorded in the manifest.

## Gates
- G6 approves exact pinned versions/digests of Python, WinSW and agent artifacts before packaging.
- G7 approves disposable hosts (Ubuntu 24.04 VM/container-equivalent, Windows Server 2022 host, Azure subscription/RG/VM allowlist) and the test window; production infrastructure is never used.
