# TLS Trust Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Explicit private-CA support across downloads, enrollment and service.
**Architecture:** Optional explicit CA arguments cross sudo boundaries. Installer
persists root-owned trust; HTTPX uses a verified SSL context for custom bundles.
**Tech Stack:** Python, HTTPX, Bash, TypeScript, pytest, Vitest.
**Spec:** docs/superpowers/specs/2026-11-21-tls-trust-contract-design.md

## Global Constraints
- Local worktree only; no VM changes, privilege grants, merge, push or deployment.
- Preserve default trust and hostname verification; never mutate frozen artifact.
- No private keys or deployment certificates in repository/artifact.

## Review Focus
- Malformed, relative, whitespace and shell-metacharacter CA paths fail safely.
- sudo sanitization cannot drop custom trust; arguments carry configuration.
- Enrollment and service use identical persisted trust after source removal.
- Service account cannot modify root-owned CA trust and can read it.
- New release pins agree and old release remains immutable.

### Task 1: Agent trust
- [x] Add failing tests for default/custom verifying context and invalid CA.
- [x] Implement optional --ca-bundle through every control-plane Sender path.
- [x] Run agent regressions.

### Task 2: Installer and command propagation
- [x] Add failing tests for policy/generator and POSIX persistence helper behavior.
- [x] Implement explicit CA path across curl, sudo, installer and systemd.
- [x] Verify validation, ownership/readability, persistence and default mode.

### Task 3: Release and review
- [x] Build new release from pinned wheels; update backend/frontend pins.
- [x] Update operator instructions and acceptance status.
- [x] Independently review changes and address findings with tests.
- [x] Run focused and full applicable regressions; record evidence.
- [ ] Commit local changes, report SHA and artifact digest without live PASS.

## Execution ledger

Ruling: execute inline following repeated PROCEED, retaining one independent
review; the earlier explicit-argument approach is the implementation choice.
Ruling: restrict custom trust in the wizard to the verified telemetry-only
installer, rather than silently generate unsupported legacy executor commands;
cost is no legacy executor wizard private-CA support.
Ruling: test persistence helper in unprivileged POSIX sandbox and unit wiring
statically, not full root installer execution; cost is a remaining live installer
and service-account verification gap, explicitly recorded in acceptance report.
Independent review: restrictive umask directory bug corrected with explicit mode;
UI input and new release pins supplied. All five production Sender constructions
were independently inspected for CA propagation. No bypass found.
Verification: 515 passed/11 skipped Python; 10 POSIX tests passed separately;
162 frontend tests passed; TypeScript/Vite build passed. See acceptance report.
