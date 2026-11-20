# Session 2 QA reconciliation — partial review candidate

Base: `9db0f8602f3b495dcd70110ae799dfb1c6c797b4`.
Existing WIP was retained, including migration startup, ownership regression
tests, schema-baseline adjustments, and revocation-revision changes.
No deployment, Azure modification, or tunnel change was performed.

## Acceptance checklist

- [x] Shared bootstrap issuance rejects HELD/RECONCILING ownership with
  `409 TARGET_ALREADY_MANAGED`, for enroll and reenroll intent.
- [x] Explicit revocation invalidates outstanding hostname-scoped bootstrap
  tokens and grants associated through expected/result host or target host.
- [x] Every explicit revoke increments the revision and records HOST_REVOKED
  with the new revision, including repeated revokes.
- [ ] Confirmed Re-enroll for revoked hostnames in the Add Server flow.
- [x] Bootstrap re-enrollment clears both previous-credential grace slots.
- [ ] Resolve short-hostname versus FQDN explicitly without weakening token scope.
- [x] Wizard registration and shared onboarding hook bind to consumed_by_host_id.
- [x] Wizard completion requires ONLINE, non-revoked identity and heartbeat,
  telemetry, and metrics timestamps after consumption, within 90 seconds and not
  in the future.
- [ ] Deliver verified version-pinned artifacts to a clean target host.

## Explicit remaining acceptance blockers

1. The existing Re-enroll dialog issues on open. The wizard merely links to the
   detail page. Neither proves explicit confirmation in the dashboard-first flow.
2. Agent enrollment uses socket.gethostname(); installer commands do not convey
   the dashboard hostname. FQDN-scoped tokens can therefore mismatch short names.
   Do not resolve this by accepting ambiguous short-name aliases server-side.
3. Install commands assume an existing /opt/nimbusops checkout and account.
   No verified downloadable installer, pinned manifest, checksum rejection test,
   or clean-machine installation has been delivered by this patch.
4. Concurrent lifecycle admission is not proven. Revision increment is currently
   an ORM read/modify/write; concurrent revokes can lose increments. Ownership
   checks cover issuance but not consumption of a token minted before ownership
   acquisition. Grant invalidation is tested as persisted state, not a concurrent
   admission CAS. These are lifecycle acceptance blockers, not passed schema tests.
5. Polling still lists only 50 bootstrap records. No exact-ID lookup or missing-
   token recovery is delivered. Browser E2E and clean-host install not run.

## Verification

- Baseline focused run: 84 passed, 3 failed, 1 warning (the three reported guards).
- Focused final backend run: 90 passed, 1 warning.
- `python -m pytest -q`: 453 passed, 1 skipped, 3 deprecation warnings.
- `$env:TZ='Asia/Jakarta'; npm test -- --reporter=dot`: 142 passed across
  23 files; React Router warnings. Review found offsetless SQLite timestamps
  were interpreted as local time; UTC parsing fixed after a failing regression.
- `npm run build`: TypeScript and Vite successful.
- `git diff --check`: no whitespace errors (Git emitted CRLF conversion warnings).
- Ruff found existing import ordering, nested-if and unused-variable findings in
  hosts.py. The added enrollment import spacing was corrected; no unrelated
  cleanup was undertaken. Strict mypy/Black and browser E2E were not run.
- `npm ci --ignore-scripts` reported 8 dependency vulnerabilities (5 moderate,
  1 high, 2 critical). No forced dependency upgrades or lockfile changes made.

This is a partial review candidate, **not** dashboard-first acceptance or release
approval. Big Pickle should verify both fixed behavior and the blockers above.
