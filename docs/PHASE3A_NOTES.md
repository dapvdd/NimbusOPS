# Phase 3A architecture notes

## Identity and isolation

Real identities use the API's immutable host UUID, never hostname as a routing key.
The current enrollment implementation must be reviewed before claiming rename-safe
re-enrollment: a unique hostname is not proof of machine identity. Future rename
must authenticate the existing UUID and change only display metadata.

Simulations use `sim-<uuid>` in browser-local `nimbusops.sim-registry.v1` storage.
They never enter backend telemetry tables. Creation and confirmed removal update
only that store. Removal entries remain locally until browser storage is cleared.
The API request boundary rejects simulated resource IDs and simulated `host_id`
payloads before fetch. Simulation views do not render real operational controls.
This frontend guard is defense in depth, not backend authorization.

Real environment metadata is absent from the API, so the UI says unspecified
rather than inventing a production designation.

## Proposed secure enrollment (NOT IMPLEMENTED)

1. Authenticate an operator and authorize enrollment for a specific scope.
2. Issue a cryptographically random one-time token with a short expiry (proposed
   ten minutes). Store only its digest, expiry, scope, issuer and consumption state.
3. Deliver the secret once over TLS; exclude it from URLs, access logs, analytics,
   error messages and audit payloads. Do not embed it in logged shell commands.
4. Atomically consume the token and issue a server-generated immutable UUID and
   per-agent credential. Concurrent replay and expired tokens must fail.
5. Record secret-free issuance/consumption events. Rate-limit attempts and verify
   authorization, expiry, replay and concurrent consumption with backend tests.
6. Re-enrollment/rotation must prove possession or use an explicit authorized
   recovery process; hostname equality must never grant an existing identity.

The existing static-token enrollment is not this contract. The dashboard does not
call it and truthfully shows NOT IMPLEMENTED for Add Existing Server.

## Proposed unregister (NOT IMPLEMENTED)

Require operator authorization, explicit identity confirmation and protected-host
policy keyed by immutable UUID (including DavidLab). Revoke credentials atomically
before disconnecting; reject future telemetry/command polling and prevent new
operations. Reconcile queued/in-flight work explicitly. Retain host tombstones,
telemetry and append-only audit history. Never cascade-delete a host to unregister
it. VM destruction and Docker deletion are separate operations and permissions.

## Current limitations

- Browser-local simulation history is not a durable audit service.
- Synthetic monitoring currently displays static samples, not a historical chart.
- Overview and Monitoring reuse the Phase 2 real-host detail presentation.
- Activity exposes only the latest operation per deployment, as supplied by API.
- Mobile navigation currently wraps above content rather than using a drawer.
- Sidebar collapse is session-local, not persisted.
- Real enrollment/removal remain unavailable. No production deployment performed.
