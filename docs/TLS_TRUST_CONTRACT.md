# Control-plane TLS trust

The `dualmode2` verified telemetry installer supports optional private/enterprise
CA trust without changing system CA stores, certifi, or public-CA defaults.
Never supply a CA signing key: only PEM CA certificates belong in this contract.

## Operator configuration

Provision the public CA bundle to the target through an already authenticated
administrative channel. Example path: `/etc/nimbusops-trust/enterprise.pem`.
Use root-owned directories (0755) and a root-owned file (0644). Every ancestor
must be root-owned, non-symlink and not group/world writable; `/tmp` is unsuitable.
Paths must be absolute, use letters/digits/underscore/dot/slash/hyphen only, and
have no `..` components. The CA file is not a secret but its integrity is critical.

- **Manual Bootstrap:** enter the target-local path in **Private CA bundle path**
  in the manual wizard. Leave empty for existing default trust. The generated
  telemetry-only command passes `--cacert` to curl and `--ca-bundle` to the
  installer after `sudo`, without `sudo -E`. Custom trust is not supported by the
  legacy Docker-executor wizard commands; that mode is disabled when a custom
  bundle is selected. Do not remove trust flags from generated commands.
- **Automatic Setup:** add optional `"ca_bundle": "/etc/nimbusops-trust/enterprise.pem"`
  to the operator-controlled SSH target policy. It is a path **on the target**,
  not the API/worker machine. Browser/API users cannot choose it. Dispatch passes
  it explicitly inside the privileged script to curl and installer. Do not
  expect the worker's environment to survive sudo.
- **Agent CLI:** `--ca-bundle /absolute/bundle.pem` is supported for enrollment,
  the normal loop, reenrollment, and credential-file verification. CLI validation
  requires a readable file containing usable CA certificates and no private key.

The installer validates custom trust before package/account mutations, then
validates again when persisting it. It atomically writes
`/etc/nimbusops-agent/ca-bundle.pem` (root-owned 0644), in a root-owned 0755
directory, and verifies readability as `nimbusops-agent`. An existing directory
with another mode is rejected, not silently repaired. Both foreground enrollment
and the generated systemd ExecStart explicitly reference this persisted copy.
The service cannot modify it. Removing the original source does not remove
persistent trust. No environment preservation or system-wide CA installation is
required. Package-manager repository TLS remains governed by OS/APT policy.

## Trust semantics and lifecycle

A custom bundle **replaces**, rather than augments, the agent connection's trust
roots. Supply a combined private/public bundle if both are needed. HTTPX receives
an explicit SSL context with certificate and hostname verification enabled;
inherited SSL_CERT_FILE does not override this explicit choice. Without a custom
bundle, HTTPX/curl keep their previous defaults (including their normal operator
environment behavior). HTTPS origins and archive SHA-256 checks remain mandatory.

For CA rotation, provision the replacement through the authenticated administrative
channel and update the root-owned persisted bundle atomically, then restart the
service and verify a fresh heartbeat and telemetry. Do not edit certifi or disable
verification. To return to default trust, remove the explicit `--ca-bundle` option
from the managed unit, daemon-reload/restart, and remove the dedicated persisted
bundle only after confirming no other process uses it. Acceptance cleanup must
also remove target-policy references, source bundles and temporary HTTPS resources.

Root administrators and the authenticated provisioning policy remain trust
authorities. They must protect the CA source against concurrent modification.
Tests do not substitute for live systemd, private-network TLS and telemetry proof.
