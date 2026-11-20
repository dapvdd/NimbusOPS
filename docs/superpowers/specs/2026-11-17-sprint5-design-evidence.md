# Sprint 5 design evidence and approval gate

Date: 2026-11-17. Documentation only; no feature implementation or live target operations.

## Workspace

- Native OpenCode worktree created at `C:\Users\user\.local\share\opencode\worktree\2bef8e\sprint5-full-design`.
- New branch `sprint/zero-touch-provisioning` created from exact commit `f3a8809c74a227dd41a801da071e9617105f8814`; verified by `git rev-parse HEAD` before documentation commit.
- Native worktree initially detached at main; clean status verified before switching to the approved immutable baseline. No reset or cherry-pick.
- Active UX worktree observed at `d77038604fb6fe09888758d174c8749867a1bda5`; its existing changes were not adopted or modified. No stash operation, merge, push, infrastructure operation or service change.

## Files / coverage

`2026-11-17-sprint5-full-design.md` covers approved architecture and alternatives, component ownership/trust, canonical mapping/approval, state transitions, additive SQLite schema/migration, lease/ownership/dispatch fencing and uncertainty, provider interface/contracts, managed credential commit and persistent-runtime proof, Linux/Windows lifecycle, API authorization, wizard/progress/history, failure/cancel/recovery, dependency-aware TDD packages, acceptance/rollback and unresolved provider gates.

`2026-11-17-sprint5-openapi.json` is an additive OpenAPI 3.1 design contract, not a generated/runtime API. Existing legacy heartbeat/telemetry are not redefined; optional proof schemas are included. No routes have been implemented.

## Validation evidence

- `node C:\Users\user\AppData\Local\Temp\opencode\validate-sprint5-contract.cjs docs/superpowers/specs/2026-11-17-sprint5-openapi.json`: JSON parse/local-reference/operation-ID/path-parameter/required-field structural checks passed: **12 paths, 13 operations, 73 references, 0 errors**. Validator created only in approved temp storage; no product code/dependencies.
- `git diff --cached --check`: passed with no whitespace errors. Staged scope: exactly three design/specification/evidence files; no application source changes. Final structural check repeated after reviewer corrections with the same 12 paths / 13 operations / 73 references / zero structural errors.
- Standard Redocly/Prism executables and Python openapi-spec-validator/jsonschema were unavailable in the inspected environment. **Redocly lint and Prism mock-contract validation have not run.** No dependency installation was performed. Structural checks are NOT equivalent to full OpenAPI lint, schema validation, example validation or contract mocks. They remain explicit implementation-entry gates.
+- Standard Redocly/Prism executables and Python openapi-spec-validator/jsonschema were unavailable in the inspected environment. **Redocly lint and Prism mock-contract validation have not run.** No dependency installation was performed. Structural checks are NOT equivalent to full OpenAPI lint, schema validation, example validation or contract mocks. They remain explicit implementation-entry gates (D0).
+- Conditional design approval (2026-11-17) closed the remaining design decisions via ADR-5.1–5.7 (WinSW pinning/provenance, Windows pipe manager transport/auth, Linux SSH contract, Azure Run Command + identity bootstrap + RBAC, OS/artifact matrix, disposable test-target policy, candidate-commit disposition). An ADR cross-review against §15 found six must-fix gaps; all six were resolved in the ADRs (receipt-TTL subordinated to admission closure, revocation serialization predicates, concrete peer-SID verification path, Azure manager-RPC router authority, both runCommands read actions pinned, nbf/token-class checks). WinSW exact tag/digest confirmation at packaging is deliberately retained as a G6 packaging action.
- No application tests/build were rerun for this documentation-only task. Prior audit baseline results are historical and explicitly labeled in the design; no new real OS/Azure acceptance claimed.
- Microsoft Learn Managed Run Command Linux documentation was fetched read-only. It explicitly describes durable named resources/status lookup and Windows protected parameters passed as process arguments. An initial generic documentation URL returned404; the OS-specific URL succeeded. No authenticated Azure API call was made.

## Independent review

Fresh general-purpose builder reviewer read both design and contract. Initial review raised seven material questions: late sender admission, revocation revision, cross-provider machine ownership, manager/runtime proof protocol, approval continuation, mode/status contract contradictions and authoritative Azure identity binding.

Normative §15 was added to resolve those questions; OpenAPI Config/CredentialCommit were corrected, baseline environment enum and cookie name checked against source. A follow-up review concluded: **sufficient for design-for-approval; no remaining material blocker among those seven at that approval level**. It explicitly did not certify provider contracts as code-ready or verified.

Mandatory carry-forward: D0 freezes exact manager wire schemas/authentication/crash fixtures and validates public OpenAPI with standard tools before implementation; schema planning must incorporate §15 fields/global machine ownership rather than using earlier abbreviated tables literally; G1–G7 remain binding. Reviewer made no file changes or live calls.

## Pending approvals

1. ~~Full design and recommended defaults/provider decisions~~ — conditionally approved 2026-11-17; design decisions closed via ADR-5.1–5.7.
2. Detailed implementation plan (dependency-aware, task-level tests, commits, rollback boundaries, acceptance criteria) — next deliverable; requires separate implementation approval.
3. G6 packaging evidence: exact WinSW tag/digest, Python and agent artifact digests recorded before packaging.
4. G4/G5 enablement evidence: Azure tenant/audience config, SDK/RBAC verification, disposable Azure targets.
5. G7: disposable Ubuntu/Windows/Azure targets, privileges, budget and test window before privileged tests.
6. Separate migration/release/deployment approval after acceptance evidence.

**Stop here: no application implementation, merge, live service modification or deployment is authorized.**
