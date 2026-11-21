import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiFailure } from "../api/client";
import type { Host } from "../api/types";
import { installCommands, verifiedInstallCommand } from "../lib/agentCommands";
import { guidanceFor } from "../lib/errorGuidance";
import { enrollmentProof, findHostByHostname } from "../lib/onboarding";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { CopyField } from "../ui/CopyField";
import { Field } from "../ui/Field";
import { InlineAlert } from "../ui/InlineAlert";
import { StatusBadge } from "../ui/StatusBadge";
import { Tabs } from "../ui/Tabs";
import AutomaticSetup from './AutomaticSetup';

type WizardStep = "host" | "mode" | "token" | "install" | "verify";

export default function Onboarding() {
  const [method, setMethod] = useState<'automatic' | 'manual'>('automatic');
  return <div className="space-y-6">
    <h1 className="text-3xl font-semibold">Add Server</h1>
    <nav aria-label="Setup method" className="flex gap-3">
      <Button aria-pressed={method === 'automatic'} onClick={() => setMethod('automatic')}>Automatic Setup (recommended)</Button>
      <Button aria-pressed={method === 'manual'} onClick={() => setMethod('manual')}>Manual Bootstrap</Button>
    </nav>
    {method === 'automatic' ? <AutomaticSetup /> : <ManualOnboarding />}
  </div>;
}

export function ManualOnboarding() {
  const navigate = useNavigate();

  const [step, setStep] = useState<WizardStep>("host");
  const [hostname, setHostname] = useState("");
  const [caBundle, setCaBundle] = useState("");
  const [mode, setMode] = useState<"telemetry-only" | "executor">("telemetry-only");

  // Host existence check state
  const [existingHost, setExistingHost] = useState<Host | null>(null);
  const [checkingFleet, setCheckingFleet] = useState(false);
  const [fleetCheckError, setFleetCheckError] = useState<string | null>(null);

  // Token issuance state
  const [issuing, setIssuing] = useState(false);
  const [issueError, setIssueError] = useState<ApiFailure | Error | null>(null);
  const [reenrolling, setReenrolling] = useState(false);
  const [tokenData, setTokenData] = useState<{
    id: string;
    token: string;
    expires_at: string;
  } | null>(null);

  // Polling verify state
  const [hostRecord, setHostRecord] = useState<Host | null>(null);
  const [onboardingReady, setOnboardingReady] = useState(false);
  const [tokenConsumed, setTokenConsumed] = useState(false);
  const [tokenExpired, setTokenExpired] = useState(false);
  const [polling, setPolling] = useState(false);

  // Clear in-memory token on unmount for security
  useEffect(() => {
    return () => {
      setTokenData(null);
    };
  }, []);

  // Poll for token consumption and host appearance during verify step
  useEffect(() => {
    if (step !== "verify" || !tokenData) return;

    let mounted = true;
    const checkStatus = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        setPolling(true);
        const [tokenRes, hostRes] = await Promise.all([
          api.listBootstrapTokens({ limit: 50 }),
          api.listHosts(),
        ]);
        if (!mounted) return;

        const currentToken = tokenRes.tokens.find((t) => t.id === tokenData.id);
        if (currentToken) {
          if (currentToken.consumed_at) {
            setTokenConsumed(true);
          } else if (new Date(currentToken.expires_at).getTime() <= Date.now()) {
            setTokenExpired(true);
          }
        }

        const proof = enrollmentProof(currentToken, hostRes.hosts);
        setHostRecord(proof.host);
        setOnboardingReady(proof.ready);
      } catch {
        // Network blips during poll are ignored
      } finally {
        if (mounted) setPolling(false);
      }
    };

    void checkStatus();
    const timer = setInterval(() => {
      void checkStatus();
    }, 3000);

    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [step, tokenData, hostname]);

  // Handle Step 1 submit
  const handleHostSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = hostname.trim();
    if (!trimmed) return;

    setCheckingFleet(true);
    setExistingHost(null);
    setFleetCheckError(null);
    try {
      const fleet = await api.listHosts();
      const existing = findHostByHostname(fleet.hosts, trimmed);
      if (existing) {
        setExistingHost(existing);
        return;
      }
      setStep("mode");
    } catch (err) {
      // The duplicate check could not run. Issuing an 'enroll' token anyway
      // would hand the operator a token that can never be consumed
      // (HOSTNAME_TAKEN at consumption). Stay on this step and say why.
      setFleetCheckError(
        err instanceof ApiFailure
          ? `Could not check whether ${trimmed} is already enrolled: ${err.message}`
          : "Could not check whether this hostname is already enrolled. Retry before issuing a token.",
      );
    } finally {
      setCheckingFleet(false);
    }
  };

  // Handle Step 2 submit -> generate real token
  const handleConfirmedReenroll = async () => {
    if (!existingHost) return;
    setIssuing(true);
    setIssueError(null);
    try {
      const result = await api.reenrollHost(existingHost.id);
      const list = await api.listBootstrapTokens({ active: true });
      const issued = list.tokens.find(t => t.hostname.toLowerCase() === existingHost.hostname.toLowerCase());
      if (!issued) throw new Error("Token issued but lookup failed. Revoke it before retrying.");
      setTokenData({ id: issued.id, token: result.bootstrap_token, expires_at: result.expires_at });
      setReenrolling(true);
      setMode("telemetry-only");
      setStep("token");
    } catch (err) {
      setIssueError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setIssuing(false);
    }
  };

  const handleGenerateToken = async () => {
    setIssuing(true);
    setIssueError(null);
    try {
      const result = await api.issueBootstrapToken(hostname.trim());
      setTokenData({
        id: result.id,
        token: result.token,
        expires_at: result.expires_at,
      });
      setStep("token");
    } catch (err) {
      setIssueError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setIssuing(false);
    }
  };

  // Revoke active token and reissue
  const handleRevokeAndReissue = async () => {
    setIssuing(true);
    setIssueError(null);
    try {
      // Find active token for this hostname and revoke it
      const activeList = await api.listBootstrapTokens({ active: true });
      const activeToken = activeList.tokens.find(
        (t) => t.hostname.trim().toLowerCase() === hostname.trim().toLowerCase()
      );
      if (activeToken) {
        await api.revokeBootstrapToken(activeToken.id);
      }
      // Re-issue
      const result = await api.issueBootstrapToken(hostname.trim());
      setTokenData({
        id: result.id,
        token: result.token,
        expires_at: result.expires_at,
      });
      setStep("token");
    } catch (err) {
      setIssueError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setIssuing(false);
    }
  };

  const legacyCommands = installCommands(window.location.origin, "/var/lib/nimbusops-agent", mode);
  const validCaBundle = !caBundle || (/^\/[a-zA-Z0-9_./-]+$/.test(caBundle) && !caBundle.split("/").includes(".."));
  const verified = verifiedInstallCommand(window.location.origin, hostname.trim(), reenrolling, validCaBundle && caBundle ? caBundle : undefined);
  const commands = mode === "telemetry-only"
    ? { promptToFile: verified, systemdTab: "# The verified installer above enrolls and starts the service. Do not run it twice.", foregroundTab: "# For diagnostics: sudo journalctl -u nimbusops-agent -n 50 --no-pager" }
    : legacyCommands;

  return (
    <div className="mx-auto max-w-3xl space-y-8 py-6">
      <header className="space-y-2">
        <div className="flex items-center gap-3 text-xs text-ink-300">
          <Link to="/servers" className="hover:text-ink-100">
            Fleet
          </Link>
          <span>/</span>
          <span className="text-ink-100">Enroll server</span>
        </div>
        <h1 className="text-2xl font-semibold text-ink-50">Enroll New Server</h1>
        <p className="text-sm text-ink-300">
          Set up a persistent NimbusOps agent on physical or virtual Linux infrastructure.
        </p>
      </header>

      {/* Wizard Progress Bar */}
      <nav aria-label="Wizard Steps" className="flex items-center justify-between border-b border-ink-800 pb-4 text-xs font-medium">
        {[
          { key: "host", label: "1. Host" },
          { key: "mode", label: "2. Mode" },
          { key: "token", label: "3. Token" },
          { key: "install", label: "4. Install" },
          { key: "verify", label: "5. Verify" },
        ].map((s, idx) => {
          const isActive = step === s.key;
          const isDone =
            (s.key === "host" && step !== "host") ||
            (s.key === "mode" && step !== "host" && step !== "mode") ||
            (s.key === "token" && (step === "install" || step === "verify")) ||
            (s.key === "install" && step === "verify");

          return (
            <div
              key={s.key}
              className={`flex items-center gap-2 ${
                isActive
                  ? "text-signal-info"
                  : isDone
                  ? "text-ink-200"
                  : "text-ink-500"
              }`}
            >
              <span
                className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] ${
                  isActive
                    ? "bg-signal-info text-ink-950 font-bold"
                    : isDone
                    ? "bg-ink-700 text-ink-100"
                    : "bg-ink-850 text-ink-500"
                }`}
              >
                {idx + 1}
              </span>
              <span>{s.label.split(". ")[1]}</span>
            </div>
          );
        })}
      </nav>

      {/* STEP 1: HOST */}
      {step === "host" && (
        <Card className="p-6">
          <form onSubmit={handleHostSubmit} className="space-y-6">
            <div>
              <h2 className="text-base font-semibold text-ink-100">Server Hostname</h2>
              <p className="text-xs text-ink-300 mt-1">
                Enter the exact hostname of the server you wish to enroll. It will be bound to the bootstrap token.
              </p>
            </div>

            <Field id="hostname" label="Hostname" hint="Must match the system hostname or FQDN (1–255 characters).">
              <input
                id="hostname"
                type="text"
                required
                maxLength={255}
                value={hostname}
                onChange={(e) => {
                  setHostname(e.target.value);
                  setExistingHost(null);
                  setFleetCheckError(null);
                }}
                placeholder="e.g. edge-router-01"
                className="w-full rounded-lg border border-ink-600 bg-ink-900 px-3 py-2 text-sm text-ink-100 focus:border-signal-info focus:outline-none"
                autoFocus
              />
            </Field>

            <Field id="ca-bundle" label="Private CA bundle path (optional)" hint="Target-local, root-controlled PEM file. Leave empty for default public CA trust. Supported by the verified telemetry-only installer.">
              <input id="ca-bundle" type="text" value={caBundle} pattern="/[a-zA-Z0-9_./-]+" onChange={(e) => { setCaBundle(e.target.value); if (e.target.value) setMode("telemetry-only"); }} className="w-full rounded-lg border border-ink-600 bg-ink-900 px-3 py-2 text-sm text-ink-100" />
            </Field>
            {!validCaBundle && <InlineAlert variant="bad" title="Invalid CA path">Use an absolute path without spaces, shell characters or parent traversal.</InlineAlert>}

            {fleetCheckError && (
              <InlineAlert variant="bad" title="Duplicate check failed">
                {fleetCheckError} The check must succeed before a token can be issued, otherwise
                the token could never be consumed (the control plane rejects enrollment of an
                existing hostname).
              </InlineAlert>
            )}

            {existingHost && (
              <InlineAlert
                variant="warn"
                title="Host already exists in your fleet"
                action={
                  <div className="flex items-center gap-3 mt-2">
                    <Link
                      to={`/servers/${existingHost.id}`}
                      className="text-xs font-semibold text-signal-warn hover:underline"
                    >
                      Open host
                    </Link>
                    {existingHost.is_revoked && <Button type="button" disabled={issuing} onClick={() => void handleConfirmedReenroll()}>Confirm re-enroll</Button>}
                  </div>
                }
              >
                A host named <strong className="font-mono">{existingHost.hostname}</strong> is already registered.
                Confirm re-enrollment only for a removed/revoked host. This issues a new single-use credential for the same host identity.
              </InlineAlert>
            )}

            {issueError && <InlineAlert variant="bad" title="Re-enrollment failed">{issueError.message}</InlineAlert>}

            <div className="flex justify-end gap-3 pt-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => navigate("/servers")}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                disabled={!hostname.trim() || checkingFleet || !!existingHost || !validCaBundle}
                loading={checkingFleet}
              >
                Continue
              </Button>
            </div>
          </form>
        </Card>
      )}

      {/* STEP 2: MODE */}
      {step === "mode" && (
        <Card className="p-6 space-y-6">
          <div>
            <h2 className="text-base font-semibold text-ink-100">Select Agent Mode</h2>
            <p className="text-xs text-ink-300 mt-1">
              Configure what capabilities the agent will run with on <strong className="font-mono">{hostname}</strong>.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <label
              className={`flex cursor-pointer flex-col justify-between rounded-lg border p-4 transition-colors ${
                mode === "telemetry-only"
                  ? "border-signal-info bg-signal-info/10"
                  : "border-ink-700 bg-ink-900 hover:border-ink-600"
              }`}
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-ink-100">Telemetry only</span>
                  <span className="rounded bg-signal-info/20 px-1.5 py-0.5 text-[10px] font-medium text-signal-info">
                    Recommended
                  </span>
                </div>
                <p className="text-xs text-ink-300 leading-relaxed">
                  Collects system telemetry (CPU, RAM, disk, load, network) and reports heartbeat status. No Docker execution.
                </p>
              </div>
              <input
                type="radio"
                name="mode"
                value="telemetry-only"
                checked={mode === "telemetry-only"}
                onChange={() => setMode("telemetry-only")}
                className="sr-only"
              />
            </label>

            <label
              className={`flex cursor-pointer flex-col justify-between rounded-lg border p-4 transition-colors ${
                mode === "executor"
                  ? "border-signal-info bg-signal-info/10"
                  : "border-ink-700 bg-ink-900 hover:border-ink-600"
              }`}
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-ink-100">Docker executor</span>
                </div>
                <p className="text-xs text-ink-300 leading-relaxed">
                  Collects telemetry and enables container deployments. Requires Docker access on the host.
                </p>
              </div>
              <input
                type="radio"
                name="mode"
                value="executor"
                disabled={!!caBundle}
                checked={mode === "executor"}
                onChange={() => setMode("executor")}
                className="sr-only"
              />
            </label>
          </div>

          <InlineAlert variant="info" title="Docker Permission Guard">
            Docker execution is disabled by default server-side until explicitly authorized by an operator on the host detail page.
          </InlineAlert>

          {issueError && (
            <InlineAlert
              variant="bad"
              title={guidanceFor(issueError).title}
              action={
                issueError instanceof ApiFailure && issueError.code === "BOOTSTRAP_TOKEN_ACTIVE" ? (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={handleRevokeAndReissue}
                    loading={issuing}
                  >
                    Revoke and reissue
                  </Button>
                ) : undefined
              }
            >
              {guidanceFor(issueError).detail}
            </InlineAlert>
          )}

          <div className="flex justify-between items-center pt-2">
            <Button type="button" variant="ghost" onClick={() => setStep("host")}>
              Back
            </Button>
            <Button
              type="button"
              variant="primary"
              onClick={handleGenerateToken}
              loading={issuing}
            >
              Generate Enrollment Token
            </Button>
          </div>
        </Card>
      )}

      {/* STEP 3: TOKEN */}
      {step === "token" && tokenData && (
        <Card className="p-6 space-y-6">
          <div>
            <h2 className="text-base font-semibold text-ink-100">Single-Use Bootstrap Token</h2>
            <p className="text-xs text-ink-300 mt-1">
              Token generated for <strong className="font-mono">{hostname}</strong>. Copy it now; it is kept only in memory and cannot be shown again.
            </p>
          </div>

          <CopyField value={tokenData.token} label="Bootstrap Token" />

          <InlineAlert variant="warn" title="Single-Use Security Notice">
            This token is valid for the TTL the control plane issued (10 minutes by default) and
            will be consumed immediately when the agent enrolls. If you leave or refresh without
            enrolling, revoke this token from Settings and issue a new one — or simply let it
            expire.
          </InlineAlert>

          <div className="flex justify-between items-center pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setTokenData(null);
                setStep("mode");
              }}
            >
              Back
            </Button>
            <Button
              type="button"
              variant="primary"
              onClick={() => setStep("install")}
            >
              Continue to Installation
            </Button>
          </div>
        </Card>
      )}

      {/* STEP 4: INSTALL */}
      {step === "install" && (
        <Card className="p-6 space-y-6">
          <div>
            <h2 className="text-base font-semibold text-ink-100">Run Agent On Host</h2>
            <p className="text-xs text-ink-300 mt-1">
              Execute these commands on <strong className="font-mono">{hostname}</strong>. The bootstrap token is entered securely into a protected 0600 file.
            </p>
          </div>

          <div className="space-y-4">
            <div>
              <h3 className="text-xs font-semibold text-ink-200 uppercase tracking-wider mb-2">
                Step A: Verified Install (Prompt-to-File)
              </h3>
              <p className="text-xs text-ink-300 mb-2">
                Paste this command into your host shell. You will be prompted to paste your bootstrap token securely.
              </p>
              <CopyField value={commands.promptToFile} label="Shell command" />
            </div>

            <div className="pt-2">
              <h3 className="text-xs font-semibold text-ink-200 uppercase tracking-wider mb-2">
                Step B: Start Agent Service
              </h3>
              <Tabs
                defaultTab="systemd"
                tabs={[
                  {
                    id: "systemd",
                    label: "systemd (recommended)",
                    content: (
                      <div className="pt-2">
                        <CopyField value={commands.systemdTab} label="systemd setup snippet" />
                      </div>
                    ),
                  },
                  {
                    id: "foreground",
                    label: "Foreground test",
                    content: (
                      <div className="pt-2">
                        <CopyField value={commands.foregroundTab} label="Foreground run command" />
                      </div>
                    ),
                  },
                ]}
              />
            </div>
          </div>

          <div className="flex justify-between items-center pt-2">
            <Button type="button" variant="ghost" onClick={() => setStep("token")}>
              Back
            </Button>
            <Button
              type="button"
              variant="primary"
              onClick={() => setStep("verify")}
            >
              Verify Enrollment
            </Button>
          </div>
        </Card>
      )}

      {/* STEP 5: VERIFY */}
      {step === "verify" && (
        <Card className="p-6 space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-ink-100">Enrollment Status</h2>
              <p className="text-xs text-ink-300 mt-1">
                Awaiting connection from <strong className="font-mono">{hostname}</strong>…
              </p>
            </div>
            {hostRecord && <StatusBadge status={hostRecord.status} />}
          </div>

          {tokenExpired && !hostRecord && (
            <InlineAlert
              variant="bad"
              title="Bootstrap token expired"
              action={
                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => {
                    setTokenData(null);
                    setTokenExpired(false);
                    setStep("mode");
                  }}
                >
                  Issue a new token
                </Button>
              }
            >
              The token reached its expiration deadline before the agent completed enrollment.
            </InlineAlert>
          )}

          <div className="rounded-lg border border-ink-800 bg-ink-900 p-4 space-y-3">
            <div className="flex items-center justify-between text-xs">
              <span className="text-ink-200">1. Bootstrap token issued</span>
              <span className="text-signal-good font-semibold">Done</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-ink-200">2. Token consumed by agent</span>
              <span className={tokenConsumed ? "text-signal-good font-semibold" : "text-ink-400"}>
                {tokenConsumed ? "Consumed" : "Waiting for agent…"}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-ink-200">3. Host registered in fleet</span>
              <span className={hostRecord ? "text-signal-good font-semibold" : "text-ink-400"}>
                {hostRecord ? "Registered" : "Waiting…"}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-ink-200">4. Telemetry heartbeat</span>
              <span className={onboardingReady ? "text-signal-good font-semibold" : "text-ink-400"}>
                {onboardingReady ? "Active" : "Awaiting fresh heartbeat and telemetry…"}
              </span>
            </div>
          </div>

          {!hostRecord && !tokenExpired && (
            <div className="flex items-center gap-3 text-xs text-ink-300">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-ink-600 border-t-signal-info" />
              <span>Waiting for agent enrollment… Polling every 3 seconds.</span>
            </div>
          )}

          {tokenExpired && !hostRecord && (
            <div className="flex items-center gap-3 text-xs text-ink-300">
              <div className="h-2 w-2 rounded-full bg-signal-bad" />
              <span>
                The token has expired without being consumed. Nothing enrolled; issue a new token
                from step 2 to try again.
              </span>
            </div>
          )}

          <div className="flex justify-between items-center pt-2">
            <Button
              type="button"
              variant="secondary"
              onClick={async () => {
                setPolling(true);
                try {
                  const [tokenRes, hostRes] = await Promise.all([
                    api.listBootstrapTokens({ limit: 50 }),
                    api.listHosts(),
                  ]);
                  const ct = tokenRes.tokens.find((t) => t.id === tokenData?.id);
                  setTokenConsumed(!!ct?.consumed_at);
                  const proof = enrollmentProof(ct, hostRes.hosts);
                  setHostRecord(proof.host);
                  setOnboardingReady(proof.ready);
                } catch {
                  // A failed manual refresh keeps the previous state; polling
                  // continues and the last-read values stay visible.
                } finally {
                  setPolling(false);
                }
              }}
              loading={polling}
            >
              Refresh Status
            </Button>

            <Button
              type="button"
              variant="primary"
              disabled={!onboardingReady}
              onClick={() => {
                if (hostRecord) {
                  navigate(`/servers/${hostRecord.id}`);
                }
              }}
            >
              Continue to Host
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
