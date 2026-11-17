# ADR-5.6 — Disposable test targets and test authorization policy

- Status: ACCEPTED (design decision, 2026-11-17; actual targets reserved by G7 before privileged tests run)
- Context: Design §12/§13 separates mock/loopback evidence from real OS/Azure acceptance. The operator approved isolated disposable hosts and prohibited production infrastructure.

## Test environment classes (evidence labels)

| Class | Environment | What it may prove |
|---|---|---|
| A: unit/contract | local dev, fake adapters/clock | logic, schema, fences, dedup, denial paths |
| B: loopback integration | local HTTP+SQLite, fake provider | API/worker/agent flow correctness |
| C: real OS | disposable Ubuntu 24.04 (VM or bare) + disposable Windows Server 2022 (VM or bare), host-keyed snapshots for repeatable runs | install, systemd/WinSW persistence, reboot, upgrade, rollback, credential handoff |
| D: real Azure | approved disposable subscription/RG/VM allowlist | RBAC denial/allow behavior, Run Command dispatch, managed-identity exchange, lost-response reconciliation |

## Rules
- Every C/D run starts from a fresh snapshot/reimage; no run assumes prior state; credentials minted during tests are test-scoped and revoked after.
- Production infrastructure, live customer hosts, and the active Sprint 4 development machines are never C/D targets.
- Azure D-runs: only allowlisted RG/VMs; cost budget cap approved with G7; test resources deleted only after evidence capture, deletion itself never part of a provisioning job.
- Test authorization is recorded per run (operator approval reference, scope, window, revocation evidence); runs without recorded authorization do not happen.
- Failure injection (kill points, network loss, disk full) lives in classes A–C; D adds provider-side uncertainty (lost response, revoked mid-flight).
- Test data: no real secrets, no production DB copies, synthetic telemetry only.

## What each remaining gate still needs (not resolvable by design alone)
- G7: operator selects and approves actual disposable hosts/subscription and budget before D-runs and any privileged C-run beyond the operator's own machines.
- G6: exact pinned artifact digests recorded before packaging (WinSW, Python, agent release).
- D0: Redocly/Prism validation and manager wire fixtures frozen before implementation.
