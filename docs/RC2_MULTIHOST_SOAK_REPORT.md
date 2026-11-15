# RC2 Multi-Host Soak Report

**Verdict: BLOCKED — not executed for RC2.**

A ≥60-minute, two-host soak with outage/recovery and operation-result criteria
was not performed. The prior run-6/run-7 harness evidence in
`.worktrees/rc1-validation` was preserved untouched but belongs to RC1; it is
not RC2 evidence and is not presented as such.

## Why it is blocked

- No isolated Docker Engine is available on this machine (see
  `RC2_DOCKER_RUNTIME_ACCEPTANCE.md`), so the Docker side of a soak cannot be
  exercised.
- A valid soak needs two independently enrolled hosts. The only reachable hosts
  are protected production systems (DavidLab, SPECTRA, MAMMON, DCC); using them
  is out of scope and was not attempted.
- Starting a two-host soak is not a code task; it needs environment and time
  authorization.

## What RC2 does provide toward soak confidence

- Claim expiry/requeue is exercised (`test_recovery.py`), and RC2 adds fencing
  so a delayed result cannot win after a requeue.
- Concurrent submission, duplicate delivery, and concurrent deploy are tested
  (`test_rc2_transactions.py`).
- The agent survives tokenless restart (F02) and refuses Docker work when the
  control plane disables it (F04).
- The backend remains up and honestly reports `degraded` if its DB fails (F12).

These are unit/integration properties, not sustained-load evidence.

## Pre-declared soak plan (for the unblocking window)

Setup:
- Control server at the candidate commit with `NIMBUSOPS_BUILD_SHA` recorded.
- Two clean hosts, each with an isolated Docker Engine, enrolled with
  operator-issued bootstrap tokens.
- Sample interval 30 s; duration **≥60 min** continuous.
- One planned control-plane outage and one agent restart per host.

Metrics collected continuously:
- heartbeat freshness gaps, telemetry gaps, poll errors, result-delivery
  failures, claim timeouts/requeues, duplicate deliveries, `UNKNOWN` operations.

Pass criteria (all must hold):
1. ≥99% of expected heartbeats present for both hosts over the window.
2. No confirmed result lost: every submitted operation reaches a terminal state
   or is visibly requeued and completed.
3. No operation applied twice after a crash/restart of the agent.
4. No unauthorized/mislabeled container mutation.
5. Control-plane outage is survived: agents resume with no credential loss and
   no manual intervention.
6. Every `UNKNOWN` has an explainable cause; none is fabricated success.
7. Health stays truthful during the outage; `/ready` fails while degraded and
   recovers without restart.

Failure handling: any lost result, duplicate effect, or mislabeled mutation ends
the soak as FAIL and reopens the relevant defect.

## Unblock requirement

Authorization for two disposable Docker-capable hosts plus a 60+ minute window.
Until then G13 is **BLOCKED**.
