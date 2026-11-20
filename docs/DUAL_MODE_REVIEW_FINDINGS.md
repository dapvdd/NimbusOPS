# Independent local acceptance review — 2026-11-20

> Historical baseline findings (`f4c1015`). The follow-up reliability sprint
> implements A/B/C; see `DUAL_MODE_RELIABILITY_ACCEPTANCE.md` for current evidence
> and review disposition. This history is retained, not a statement that the
> baseline fixes were already accepted at the time of the original review.

Read-only fresh-context reviewer inspected the complete tracked diff against
`8203d46` plus new production/tests/policy/docs. No unrelated functional changes
identified beyond intended UTC carry-forward. No Critical finding identified.
This is **not a clean acceptance sign-off**.

## Important (unresolved — block acceptance)

1. **Confirmation response loss:** `AutomaticSetup.tsx:45–52` persists the job
   reference only after the confirm response arrives. The backend commits first;
   replay rejects consumed approval and no lookup recovers the committed job.
   SessionStorage protects reload only after a successful response. Requires
   authorized idempotent recovery and response-loss regression coverage.
2. **Cross-mode ownership host binding:** `services/provisioning.py:137–157`
   reserves ownership without `host_id`; `provisioning/worker.py:212–217` marks
   success without binding the enrolled host. Existing manual reenrollment guard
   in `services/enrollment.py:78–90` joins through ownership.host_id, so it does
   not see this automatic reservation. Requires owner/generation-checked binding
   and manual reenrollment conflict tests during VERIFYING and after success.
3. **Terminal job traps the tab:** `AutomaticSetup.tsx:69–88` hides selection
   while the persisted job reference exists. Only safe retry clears it; success
   has no “Add another” path. A missing job also polls indefinitely. Requires a
   safe local-reference dismissal/recovery flow without blind retry.

No product fixes were made in this acceptance-only pass. These findings are not
waived: the candidate is an inspectable local **NO-GO snapshot**, not a release
approval. Remediation should be a focused regression-backed follow-up, not broad
refactoring. Risk if deferred: lost progress, bypassed cross-mode exclusion,
and inability to onboard a second target in the same tab.

## Minor (deferred)

- Malformed operator JSON shape can raise TypeError/AttributeError outside the
  sanitized policy 503 handler (`ssh.py:45–46`, API `provisioning.py:30–33`).
  Operator-controlled availability issue; no browser-selected SSH target.
- Incidental schema BOM/mojibake was corrected; whitespace-only additions near
  response schemas are not material to acceptance.

## Coverage limits

Static review cannot establish real SSH, sudo, systemd, package installation,
tmpfs/swap behavior or host-key mismatch behavior on Ubuntu. Local process tests
exercise Windows locking/CAS only, not Linux flock or full stress/crash coverage.
