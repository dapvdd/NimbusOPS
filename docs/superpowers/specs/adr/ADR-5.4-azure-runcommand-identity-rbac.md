# ADR-5.4 — AZURE_VM: Managed Run Command, identity bootstrap, credential delivery and RBAC

- Status: ACCEPTED (design decision, 2026-11-17; execution details are enablement gates G4/G5)
- Context: Sprint 5 scope is agent installation/lifecycle on existing explicitly authorized VMs. Learn documentation (Linux + Windows Managed Run Command, fetched 2026-11-17) defines named Run Command resources, instanceView execution state, protected parameters passed as argv (Windows) or environment (Linux), and `treatFailureAsDeploymentFailure` from API 2023-03-01.

## Decision

### Dispatch mechanism
- Use **Managed Run Command** (named child resource `runcommands/<name>`), API version pinned **2023-03-01 or later** in the adapter manifest; unique name `nimbusops-<dispatch_uuid>` persisted before creation; never re-PUT or delete an uncertain resource (design §6).
- Set `treatFailureAsDeploymentFailure=true` so ARM provisioning state reflects script failure; still read instanceView separately — neither alone is success.
- `timeoutInSeconds` from design per-step deadlines; `asyncExecution` for install actions.

### Script and secret constraints (hard requirements)
- Run Command source carries **only** the fixed guest-manager bootstrap script (constant, versioned, digest-recorded) plus public parameters: backend base URL, job_id, dispatch_id, candidate_id, artifact URL (allowlisted HTTPS), artifact digest.
- **No secrets in**: script body, parameters, protectedParameters (Windows argv / Linux environment per Learn docs), environment, outputBlobUri, errorBlobUri, SAS URLs, or guest logs. The bootstrap secret is never embedded in the dispatch at all — see identity exchange below.
- SDK/HTTP request bodies are excluded from logging; output/error blobs are not used in the first slice.

### Identity bootstrap (VM-side managed identity)
- Target VM has a **system-assigned managed identity** enabled by the operator before enablement (not granted by this sprint).
- The guest manager bootstrap script calls IMDS to obtain a token for the dedicated NimbusOps bootstrap audience (`api://<nimbusops-app-id>` or configured identifier), keeps it in memory only, and POSTs to `POST /api/v1/agents/provisioning-grants` over TLS with job/dispatch/candidate binding.
- The backend validates: signature via cached tenant JWKS, issuer/audience/exp/nbf with bounded clock leeway, tenant ID allowlist, `oid` equals the allowlisted principal object ID for that exact VM, and explicit rejection of non-workload token classes (client-credential app-only tokens without an `oid`/VM binding, user tokens, unknown token type claims). It then performs an **authoritative ARM read** (`virtualMachines/read`) confirming the ARM resource ID + `vmId` match the approved snapshot binding (design §15.6). Fail closed on any mismatch/unavailability; cache only for read-only status (≤30s), never for mutation authorization.
- The exchange response body carries the ephemeral enrollment capability token (never in a URL, script, log or durable provider artifact).

### Credential delivery (summary of the flow)
1. Run Command dispatches fixed bootstrap script + public params.
2. Guest manager: IMDS token → grant exchange → receives capability in memory.
3. Guest manager prepares protected candidate credential file + journal PREPARED (design §7), then `POST /agents/managed-enrollments` with capability + candidate credential over TLS.
4. Backend commit/receipt per design §7/§15; manager promotes candidate after confirmed current commit; daemon starts with new Sender.
- Lost-response recovery follows design §7/§15.6 (same-grant metadata replay; replacement only after journal/DB proof).

### Manager RPC authorization (beyond grant exchange)
- All §15.4 manager messages (STATUS, ADMIT, START_ACTION, CONFIRM_ACTIVATION, ARM_CHALLENGE, CANCEL, CLOSE_RESULT) ride the **same independently authenticated VM workload identity** as grant exchange on the manager-auth router — never agent bearer, never operator cookie, never the enrollment grant. Backend validates identity + exact dispatch/machine binding per message. Wire schemas, auth rules and crash/replay fixtures freeze in D0.

### RBAC (minimum, custom role proposed; final set pinned in D0 fixtures, confirmed in G5)
- `Microsoft.Compute/virtualMachines/read`
- `Microsoft.Compute/locations/runCommands/read` (subscription-level listing; Learn: Reader and higher have this)
- `Microsoft.Compute/virtualMachines/runCommands/read` (per-VM instanceView lookup used for reconciliation)
- `Microsoft.Compute/virtualMachines/runCommands/write`
- Plus the LRO read permission the pinned SDK requires (verify in G5).
- D0 resolves the exact action list once against pinned SDK/API metadata and freezes it in contract fixtures; both read actions above are included so a wrong-single-read assumption cannot turn status lookup into UNKNOWN (§15.1).
- Explicitly excluded: Contributor, VM create/delete/start/restart, networking.*, role assignment permission, `Microsoft.Authorization/*`.
- Assignment scope: the specific resource group(s) or subscription containing allowlisted VMs only; assignment happens as operator enablement (G4), not runtime automation.

### Consequences / gates
- Missing managed identity, audience config, JWKS reachability or ARM binding mismatch → SETUP_REQUIRED/PERMISSION_DENIED with actionable remediation; adapter disabled, not degraded.
- Token class confusion (e.g. cannot reliably distinguish intended workload token type in the tenant) → adapter remains disabled pending reviewed policy (design §15.6).
- All RBAC/SDK behavior mock-tested in D7; real Azure validation only on approved disposable targets (G5/G7).
- Azure SDK: official `azure-identity` / `azure-mgmt-compute` pinned versions in the dependency manifest; no generic HTTP reimplementation of auth.
