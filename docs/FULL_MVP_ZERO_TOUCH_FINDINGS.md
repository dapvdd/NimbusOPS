# Full MVP M1 — zero-touch evidence findings

## Historical outcome remains unknown

The preserved local `AUTOMATIC_SETUP_AUTHORIZATION_B_OUTCOME.md` records a
single spent admission, no observed installation/enrollment, discarded original
stdout/stderr, and an unknown exact failure point. Missing installation does not
prove the launcher never executed. This work did not inspect historical databases,
replay an admission, or rearm spent markers. An unintended SSH invocation during
broader testing is disclosed below. No root/installer execution is established.
This does not establish a historical root cause or real-host acceptance.

## Confirmed local defect and scoped repair

The original `ssh.install` discarded both streams and preserved only nonzero SSH
status. Timeout and local transport-launch failure were indistinguishable, and
there was no separate installer exit evidence.

The fixed wrapper now emits only `NIMBUSOPS/1` records on a dedicated descriptor:
lock acquired, identity absent, archive downloaded/verified/extracted, adapter
ready, installer started, and numeric installer exit (0–255). All normal output
and stderr remain suppressed; the installer cannot inherit the protocol descriptor.
No raw diagnostics enter database events or API fields. Parsing accepts only
complete, exact allowlisted records within a 4096-byte prefix; the local reader
continues draining excess output without retaining it. This is not a general log
capture facility.

Worker events persist the observed phases, closed outcome code, and bounded numeric
installer/transport statuses after the local transport returns or raises a handled
timeout/cancellation. Admission is still committed before dispatch. Abrupt process
death can lose these later checkpoints, but never authorizes redispatch: the durable
admission and reconciliation requirement remain. No checkpoints are inferred when
the channel is absent, truncated, or lost.

The 600-second deadline kills/reaps the local SSH waiter only. `TIMED_OUT`, local
launch failure, disconnect/nonzero status, and cooperative `KeyboardInterrupt`
cancellation all retain uncertainty. Cancellation persists available safe evidence
and propagates to stop the worker. SIGKILL/power loss relies on committed admission
and restart reconciliation rather than an impossible final event guarantee.
Neither a phase nor exit zero marks provisioning successful; token-linked fresh
heartbeat and actual telemetry remain mandatory. Admitted work is never retried.

The three-argument install call and legacy adapters/mocks returning `None` remain
supported. TLS validation, custom CA propagation, strict pinned SSH trust, sudo
noninteractive behavior, identity checks, and installer adapter are preserved.
At coordinator request, only the release constants were advanced to the new
immutable `fullmvp1` artifact and supplied SHA; packaging/equality verification is
owned by the coordinator. Existing dualmode artifacts were not changed here.

## Deterministic evidence

- Before implementation, `python -m pytest backend/tests/test_provisioning_ssh.py
  backend/tests/test_provisioning_jobs.py -q`: **11 failed, 23 passed** (new interfaces
  absent). A narrower behavioral RED run, `python -m pytest
  backend/tests/test_provisioning_ssh.py -q -k keeps_only`: **3 failed, 17 deselected**;
  existing success returned `None` and failure exceptions had no safe phase/installer
  evidence.
- After implementation: the same two-file command reached **37 passed**, with one
  existing Starlette/AnyIO deprecation warning. Cases cover success, installer exit
  42, disconnect 255, timeout partial evidence, cancellation, durable safe events,
  no redispatch, arbitrary secret output, malformed protocol, bounded output, and
  a real local Python child timeout (no SSH or installer execution).
- `python -m mypy --strict --follow-imports=silent
  backend/app/provisioning/ssh.py backend/app/provisioning/worker.py`: **success,
  no issues in 2 source files**.
- `python -m ruff check --output-format concise backend/app/provisioning/ssh.py
  backend/app/provisioning/worker.py`: **all checks passed**. Black formatted the
  four owned Python files.

- A full `python -m pytest -q` attempt exceeded its 120-second deadline around
  48% after displaying five failures; no final failure names/tracebacks were
  produced before termination. A fail-fast rerun with short tracebacks was started
  to identify the first broader-suite failure; the full suite is not claimed green.
- Fail-fast `python -m pytest -q --tb=short -x`: **1 failed, 252 passed,
  10 skipped** in 54.24 seconds. Failure:
  `backend/tests/test_install_diagnostics.py::test_failed_transport_preserves_only_numeric_status[1]`
  expected mocked status 1 but observed 255. That unowned legacy test patches
  `subprocess.run`, whereas bounded transport now uses `Popen`; it therefore
  unintentionally invoked SSH against its reserved documentation address
  `192.0.2.1`. Earlier full-run failures likely share this stale mock boundary,
  but their individual names were not emitted. This violated the intended
  local-only execution boundary and is explicitly disclosed, not presented as
  acceptance. The coordinator must migrate this test file's mocks to
  `_run_install` and remove obsolete DEVNULL-kwargs assertions before any further
  broad run. No further broad run was attempted by this worker.

These are synthetic/local regression results, not Ubuntu/systemd/network or live
enrollment acceptance. Full-suite results and archive equality are reported by the
integration coordinator separately. No commit was created by this worker.
