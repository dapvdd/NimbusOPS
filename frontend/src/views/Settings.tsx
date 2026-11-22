/**
 * Settings: operator account, control-plane health/readiness, and the
 * deployment reference.
 *
 * Readiness answers with 503 while degraded; that is data, not an error, and
 * the page shows concrete diagnosis steps. There is deliberately no restart
 * button — this console never pretends it can fix the control plane.
 */

import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { HealthResponse, ReadinessResponse } from "../api/types";
import { useSession } from "../auth/Session";
import { CopyField } from "../ui/CopyField";
import { Button } from "../ui/Button";
import { formatUtcTime } from "../lib/format";

const UNIT_PATHS = [
  { label: "API unit example", value: "deploy/examples/systemd/nimbusops-api.service.example" },
  { label: "Web unit example", value: "deploy/examples/systemd/nimbusops-web.service.example" },
  {
    label: "Agent unit example (telemetry)",
    value: "deploy/examples/systemd/nimbusops-agent-telemetry.service.example",
  },
  {
    label: "Agent unit example (executor)",
    value: "deploy/examples/systemd/nimbusops-agent-executor.service.example",
  },
  {
    label: "Enrollment wrapper example",
    value: "deploy/examples/bootstrap-enroll.sh.example",
  },
];

const ENVIRONMENT_CONTRACT = [
  "NIMBUSOPS_DATABASE_URL=sqlite:///<state-dir>/nimbusops.sqlite3",
  "NIMBUSOPS_ENROLLMENT_MODE=bootstrap",
  "NIMBUSOPS_TOKEN_PEPPER=<32+ random bytes>            # backend.env mode 0600",
  "NIMBUSOPS_BROWSER_ORIGINS=https://<ui-origin>        # exact origin, never *",
  "NIMBUSOPS_CORS_ORIGINS=https://<ui-origin>           # exact origin, never *",
  "NIMBUSOPS_SESSION_COOKIE_SECURE=true                 # false only for loopback HTTP preview",
].join("\n");

export default function Settings() {
  const session = useSession();
  const user = session?.user ?? null;

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState('');

  const check = useCallback(async () => {
    setLoading(true);
    setError(null);
    const started = Date.now();
    const [healthResult, readinessResult] = await Promise.allSettled([api.health(), api.readiness()]);

    setHealth(healthResult.status === "fulfilled" ? healthResult.value ?? null : null);
    setReadiness(readinessResult.status === "fulfilled" ? readinessResult.value ?? null : null);

    const failures = [healthResult, readinessResult].filter((result) => result.status === "rejected");
    if (failures.length > 0) {
      setError(`${healthResult.status === "rejected" ? "Health" : "Readiness"} probe unavailable. Control-plane readiness is not verified; recheck before relying on it.`);
    }

    setLatencyMs(Date.now() - started);
    setCheckedAt(new Date().toISOString());
    setLoading(false);
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  const handleSignOut = async () => {
    if (!session) return;
    setSigningOut(true);
    setSignOutError('');
    try {
      await session.logout();
    } catch {
      setSignOutError('Sign-out failed. Your session has not been confirmed closed; please retry.');
    } finally {
      setSigningOut(false);
    }
  };

  const degraded =
    (readiness !== null && (!readiness.ready || readiness.database !== "ok")) ||
    (health !== null && (health.status !== "ok" || health.database !== "ok"));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-ink-400">Your account, control-plane health, and deployment reference.</p>
      </div>

      <section aria-labelledby="account-title" className="space-y-4 rounded-lg border border-ink-700 bg-ink-850 p-4">
        <h2 id="account-title" className="text-sm font-semibold uppercase tracking-wider text-ink-300">
          Account
        </h2>
        <div data-testid="settings-account" className="flex flex-wrap items-center gap-4">
          {user ? (
            <>
              <div>
                <div className="font-mono text-base font-semibold text-ink-100">{user.username}</div>
                <div className="text-xs text-ink-400">Role: {user.role}</div>
              </div>
              <Button
                type="button"
                variant="secondary"
                loading={signingOut}
                onClick={() => void handleSignOut()}
              >
                Sign out
              </Button>
            </>
          ) : (
            <p className="text-sm text-ink-400">Not signed in.</p>
          )}
        </div>
        {(signOutError || session?.error) && (
          <p role="alert" className="text-xs text-signal-warn">
            {signOutError || session?.error}
          </p>
        )}
      </section>

      <section aria-labelledby="control-plane-title" className="space-y-4 rounded-lg border border-ink-700 bg-ink-850 p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 id="control-plane-title" className="text-sm font-semibold uppercase tracking-wider text-ink-300">
            Control plane
          </h2>
          <Button type="button" variant="secondary" size="sm" loading={loading} onClick={() => void check()}>
            Recheck
          </Button>
        </div>

        {error && (
          <div role="alert" className="rounded-lg border border-signal-bad/40 bg-signal-bad/10 p-3 text-sm text-signal-bad">
            {error}
          </div>
        )}

        {loading && !readiness && !health && <p className="text-sm text-ink-400">Checking control plane…</p>}

        {degraded ? (
          <div
            data-testid="readiness-degraded"
            className="space-y-3 rounded-lg border border-signal-warn/40 bg-signal-warn/10 p-4 text-sm text-signal-warn"
          >
            <p className="font-semibold">Control plane degraded</p>
            <p className="text-xs text-ink-300">
              {readiness
                ? `The readiness probe reports ${readiness.ready ? "ready" : "not ready"} with database state ${readiness.database}.`
                : "Readiness probe unavailable; readiness is not verified."}
              {health && ` Health probe reports ${health.status} with database state ${health.database}.`}
            </p>
            <div data-testid="readiness-recovery" className="space-y-1 text-xs text-ink-200">
              <p className="font-semibold">Diagnose on the server:</p>
              <ol className="list-decimal space-y-1 pl-5 text-ink-300">
                <li>
                  Process: confirm the API service is running — the unit you installed from
                  deploy/examples/systemd/nimbusops-api.service.example (systemctl status &lt;that-unit&gt;).
                </li>
                <li>Database: check NIMBUSOPS_DATABASE_URL — path, permissions, and disk space.</li>
                <li>Logs: inspect the control-plane service logs for the failing dependency.</li>
              </ol>
              <p className="text-ink-400">This console does not restart services.</p>
            </div>
          </div>
        ) : !loading && !error && readiness?.ready && health?.status === "ok" ? (
          <div
            data-testid="readiness-ok"
            className="space-y-2 rounded-lg border border-signal-good/40 bg-signal-good/10 p-4 text-sm text-signal-good"
          >
            <p className="font-semibold">Control plane ready</p>
            <p className="text-xs text-ink-300">
              Readiness probe passed; database state {readiness?.database ?? health?.database ?? "ok"}.
            </p>
          </div>
        ) : null}

        <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
          <Fact label="Status" value={health?.status ?? "unknown"} />
          <Fact label="Database" value={health?.database ?? readiness?.database ?? "unknown"} />
          <Fact label="Version" value={health?.version ?? readiness?.version ?? "unknown"} />
          <Fact label="Build" value={health?.build ?? "unknown"} />
          <Fact label="Probe latency" value={latencyMs !== null ? `${latencyMs} ms` : "unknown"} />
          <Fact label="Last check" value={checkedAt ? formatUtcTime(checkedAt) : "never"} />
        </dl>
        {health?.server_time && (
          <p className="text-[11px] text-ink-500">Server time {formatUtcTime(health.server_time)}</p>
        )}
      </section>

      <section
        data-testid="deployment-reference"
        aria-labelledby="deployment-title"
        className="space-y-4 rounded-lg border border-ink-700 bg-ink-850 p-4"
      >
        <h2 id="deployment-title" className="text-sm font-semibold uppercase tracking-wider text-ink-300">
          Deployment reference
        </h2>
        <p className="text-xs text-ink-400">
          These are the reviewed example files in this repository. Nothing is installed by
          NimbusOps and nothing is edited from this console; an operator copies each example,
          substitutes its @TOKEN@ values, and installs it on the server (see
          deploy/examples/README.md).
        </p>

        <div className="space-y-3">
          {UNIT_PATHS.map((unit) => (
            <CopyField key={unit.value} label={unit.label} value={unit.value} />
          ))}
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium text-ink-300">Environment contract</p>
          <pre className="overflow-x-auto rounded-lg border border-ink-700 bg-ink-900/60 p-3 font-mono text-xs text-ink-200">
            {ENVIRONMENT_CONTRACT}
          </pre>
          <p className="text-[11px] text-ink-400">
            Secrets belong in 0600 files referenced by these variables — never in argv, logs, or URLs.
          </p>
        </div>
      </section>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/40 p-3">
      <dt className="text-[11px] uppercase tracking-wider text-ink-400">{label}</dt>
      <dd className="mt-1 truncate font-mono text-ink-100" title={value}>
        {value}
      </dd>
    </div>
  );
}
