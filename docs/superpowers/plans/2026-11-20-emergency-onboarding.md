# Emergency single-host onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Connect one Ubuntu 24.04 host using a verified distribution, explicit hostname and private token input.

**Architecture:** Keep the existing Python agent and bootstrap API. Build a deterministic source distribution with a pinned Linux wheelhouse, expose immutable release files through the control plane, and install a telemetry-only systemd service without a repository checkout. Preserve strict hostname scope and existing authentication.

**Tech Stack:** Python, Bash, FastAPI, React/TypeScript, pytest, Vitest.

**Spec:** User emergency sprint request (2026-11-20), priorities A–D. START NOW authorizes inline execution without a design approval round.

## Global Constraints
- No production deployment, Azure installation, tunnel or authentication changes.
- No lifecycle acceptance claim without concurrent revoke/admission verification.
- Secrets must not appear in shell history, command arguments or committed artifacts.
- Prefer a tested single-host fallback over an unproven wizard claim.

## Review Focus
- Dashboard FQDN differs from operating-system hostname: explicit identity must win.
- Corrupt downloaded artifact: fail before extraction/execution.
- Existing identity on re-add: explicit confirmed reenrollment, not silent reuse.
- Clean host lacks Python virtualenv tooling: installer names prerequisites.
- Release unconfigured or unavailable: fail closed; never invent a download URL.

### Task 1: Explicit hostname
- [x] Add failing regression for configured hostname in bootstrap payload.
- [x] Add Config hostname, CLI/env wiring and registration propagation; rerun agent tests.

### Task 2: Verified distribution and installer
- [x] Add failing tests for deterministic packaging and installer safety contract.
- [x] Implement release builder, pinned wheelhouse, private token prompt and telemetry service.
- [x] Build release twice, compare SHA-256; verify rejection of corrupt bytes in Git Bash (not Ubuntu).

### Task 3: Dashboard integration and confirmation
- [x] Add regression tests for copyable pinned commands and explicit reenroll confirmation.
- [x] Wire pinned artifact metadata and selected hostname into dashboard commands.
- [x] Finish Add Server confirmation before token issuance without weakening ownership/revocation checks. Legacy host-detail dialog unchanged.

### Task 4: Isolated validation and operator handoff
- [x] Run scratch-plane registration/heartbeat/telemetry and stable-ID lifecycle tests.
- [ ] Run affected backend/frontend tests and build; attempt browser/Ubuntu integration only in disposable environments.
- [ ] Record exact evidence, artifact hash, blockers, deployment and operator steps, demo GO/NO-GO; commit verified changes.

Progress and rulings: `docs/EMERGENCY_DEMO_RUNBOOK.md`, Evidence and review ledger.
Task 4 remains partial: Ubuntu/systemd and browser E2E acceptance blocked by environment.
