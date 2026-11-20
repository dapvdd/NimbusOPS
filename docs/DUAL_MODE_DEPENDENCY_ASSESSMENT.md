# Frontend advisory disposition — 2026-11-20

Registry evidence: `npm audit --json` exits 1 with **8 affected packages**:
5 moderate, 1 high, 2 critical. These are package-level aggregates with shared
advisories, not eight distinct exploits. `npm audit --omit=dev --json` reports
only **2 moderate** packages; no high/critical production dependency findings.
No dependency or lockfile changes were made. This is a reachability assessment,
not an exploit test or an unconditional risk acceptance.

| Package (installed) | Severity | Exposure / disposition | Remediation |
| --- | --- | --- | --- |
| `@vitest/mocker` 2.1.9 | Moderate | Dev-only: redirect-mock arbitrary file read and unauthenticated mock registration/code injection. Never expose Vitest/mocker servers to untrusted networks; run trusted tests only. Not shipped in static browser bundle. | Upgrade compatible Vitest stack to a version containing mocker >=4.1.12. Registry proposes Vitest 5.1.1; validate Node requirements and test compatibility. |
| `esbuild` 0.21.5 | Moderate | Dev server cross-origin response disclosure (GHSA-67mh-4wv8-2f99). Build tool, not browser runtime. Do not expose its serve API. | Upgrade Vite/esbuild together; patched esbuild >0.24.2. |
| `react-router` 6.30.6 | Moderate | Runtime: GHSA-wrjc-x8rr-h8h6 backslash redirect and GHSA-337j-9hxr-rhxg SSR hydration constructor injection. Application uses `BrowserRouter` and client rendering, not SSR hydration, so SSR path is not configured. Navigation targets are constants or fixed `/servers/`/`/hosts/` prefixes. Login uses router location state with a leading-slash check; that check alone does **not** prove backslash safety. No untrusted query-string redirect sink observed. Residual runtime risk remains; not declared non-exploitable. | Upgrade React Router DOM/router together to >=7.18.0 (registry proposes 7.18.6); test routing/login/splat semantics. Separately harden internal return-path validation if an untrusted return parameter is introduced. |
| `react-router-dom` 6.30.6 | Moderate | Same runtime router advisories propagated through direct dependency; not an additional independent vulnerability. | Same coordinated router upgrade. |
| `tinypool` 1.1.1 | Critical | Dev-only prototype-pollution gadgets to worker-options/run-options RCE (GHSA-5gmw-xhrv-c9v3, GHSA-85c8-ppgw-ccpr). Requires attacker-influenced/prototype-polluted options; no production Node worker runtime. Trusted test code still executes with developer privileges. | Upgrade Vitest with tinypool >=2.1.2; do not blindly override a worker-pool major version. |
| `vite` 5.4.21 | High | Dev-only: file-serving/path traversal, cross-origin middleware script execution, Windows launch-editor command/NTLM disclosure issues. Existing `npm run build` creates static output; no Vite server is needed in production. Do not use exposed `vite`/preview as the acceptance HTTPS origin. | Registry proposes Vite 8.3.8; coordinate plugin-react and Node compatibility and rerun builds. |
| `vite-node` 2.1.9 | Moderate | Dev-only propagation of Vite server risks into test executor. Not in static runtime. | Upgrade with Vitest/Vite stack. |
| `vitest` 2.1.9 | Critical | Dev-only GHSA-5xrq-8626-4rwp unauthenticated read/execute when UI server listens (patched >=3.2.6), plus mocker/tinypool/Vite propagated findings. Script is `vitest run`, not UI/API server mode. No UI server was launched by acceptance commands. | Coordinated Vitest upgrade including all transitive fixes, not merely 3.2.6. Registry proposes 5.1.1. |

## Operational constraints and release decision

- Serve only `frontend/dist` through the approved static HTTPS server; do not
  publish `node_modules`, source trees, Vite/Vitest APIs, or developer credentials.
- Keep development/test services inaccessible to untrusted peers and use trusted
  source/tests. Loopback alone is not a complete mitigation for cross-origin
  browser attacks; avoid vulnerable dev-server modes entirely where possible.
- Major framework/tool upgrades are a separate compatibility task, not an
  automatic `npm audit fix --force` during candidate acceptance.
- Advisory remediation/risk acceptance remains open before deployment. These
  findings do not require live infrastructure to assess and do not prevent an
  isolated, static-origin real-VM acceptance test under these constraints.

Evidence paths: `frontend/package.json`, `frontend/package-lock.json`,
`frontend/src/main.tsx`, `frontend/src/views/Login.tsx:14`,
`frontend/src/auth/Session.tsx:36`, navigation call sites in `frontend/src/views/`.
All advisory details came from the registry response during this session;
package inventories were checked with `npm ls` for all eight affected packages.
