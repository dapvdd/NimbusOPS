# Explicit TLS trust contract

Approved scope: local candidate remediation only; no guest or production changes.

Use explicit CA path arguments, not sudo-preserved environment. Default public
CA verification remains unchanged. A configured PEM bundle replaces the CA set
for the control-plane connection (operators needing public and private roots
must provide a combined bundle). Certificate and hostname verification remain
mandatory. No signing keys or deployment certificates ship in the release.

The manual generator accepts an optional host-local absolute CA path and passes
it to curl and the root installer. Automatic target policy accepts an optional
target-local CA path, passed explicitly inside the privileged script. The bundle
must be provisioned by the operator before dispatch; never fetched over an
untrusted channel. Installer validates it before mutation, persists a root-owned
service-readable copy, checks readability as the service user, and explicitly
passes the persisted path to enrollment and systemd execution. Agent CLI accepts
`--ca-bundle` and builds an explicit verifying SSL context for custom trust.

Alternatives: managed SSL_CERT_FILE would work but depends on environment
handling; system-wide trust/certifi modification is unnecessarily broad. Explicit
arguments and SSL context were recommended and the operator instructed PROCEED.

Validation: RED/GREEN tests for agent TLS, command propagation, policy validation,
installer execution under a sandbox, service persistence, default compatibility,
and malformed/missing/unreadable CA input. Build a newly named deterministic
artifact from pinned wheels; preserve old artifact. Independent review precedes
final regressions and local commit. Live modes remain NOT RUN.
