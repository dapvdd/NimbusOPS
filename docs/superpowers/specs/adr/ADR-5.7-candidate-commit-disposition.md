# ADR-5.7 — Disposition of design decisions 699883e and 49029a9

- Status: ACCEPTED (design decision, 2026-11-17)
- Context: The operator directed that commits `699883e` (backend lifecycle/intent guards) and `49029a9` (agent one-shot re-enroll/credential application) be evaluated as potential source material without blind cherry-picking. Design §0 records the audit verdict; this ADR fixes the disposition.

## Evaluation

### 699883e — backend effective status / mode / lifecycle guards
- Source material worth porting: effective host status computation, agent-mode reporting consistency, and durable intent/lifecycle guard patterns.
- Audit defect to avoid: intent/lifecycle patterns in that commit predate the §5/§15.1 admission protocol; they are sketches, not the final fencing contract.

### 49029a9 — agent one-shot re-enroll / apply-credential-file
- Source material worth porting: candidate-file staging, atomic identity replace, backup/restore mechanics and cross-process lock ideas in `config.py`.
- Audit defects to avoid (design §7/§15 supersedes):
  - Restoring the old invalid identity after a committed enrollment (loses valid new credential).
  - Treating a one-shot helper's successful heartbeat as verification success.
  - File replacement does not reconstruct the already-built Sender in a running daemon (stale credential use).
  - Swallowed Windows ACL failures (`config.py:102-128`) — the design makes ACL failure fatal before secret write (§8).

## Disposition
- Neither commit is merged or cherry-picked wholesale.
- D4/D5 implement the §7/§15.4 protocols with TDD; where a mechanism from these commits matches the final design (atomic replace, staging, locking), it may be re-implemented with reference to the original, with regression tests proving the audit defects cannot recur (old-identity restoration, helper heartbeat acceptance, stale Sender).
- D0 records the specific defect regression tests; D5 includes the Windows ACL fail-closed test.

## Consequences
- The Sprint 5 branch stays exactly on `f3a8809` + design commits; no source from `sprint/ux-perfection` worktree is adopted implicitly, and that worktree's active WIP remains untouched.
