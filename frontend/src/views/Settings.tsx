/**
 * Settings: operator account, control-plane health/readiness, and the
 * deployment reference.
 *
 * Readiness answers with 503 while degraded; that is data, not an error, and
 * the page shows concrete diagnosis steps. There is deliberately no restart
 * button — this console never pretends it can fix the control plane.
 */

import { useCallback, useEffect, useState } from "react";
import { api, ApiFailure } from "../api/client";
import type { HealthResponse, ReadinessResponse } from "../api/types";
import { useSession } from "../auth/Session";
import { CopyField } from "../ui/CopyField";
import { Button } from "../ui/Button";
import { formatUtcTime } from "../lib/format";

const UNIT_PATHS = [
  { label: "Backend unit", value: "/etc/systemd/system/nimbusops-backend.service" },
  { label: "Agent unit", value: "/etc/systemd/system/nimbusops-agent.service" },
  { label: "Application directory", value: "/opt/nimbusops" },
];

const ENVIRONMENT_CONTRACT = [
  "NIMBOPS_API_URL=https://<control-plane-host>/api/v1",
  "NIMBOPS_AGENT_TOKEN_FILE=/etc/nimbusops/agent-token   # mode 0600, never argv or a URL",
  "NIMBOPS_DB_PATH=/var/lib/nimbusops/nimbusops.db",
  "NIMBOPS_LOG_LEVEL=info",
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

  const check = useCallback(async () => {
    setLoading(true);
    setError(null);
    const started = Date.now();
    const [healthResult, readinessResult] = await Promise.allSettled([api.health(), api.readiness()]);

    if (healthResult.status === "fulfilled") setHealth(healthResult.value ?? null);
    if (readinessResult.status === "fulfilled") setReadiness(readinessResult.value ?? null);

    const failures = [healthResult, readinessResult].filter((result) => result.status === "rejected");
    if (failures.length === 2) {
      const reason = (healthResult as PromiseRejectedResult).reason;
      setError(reason instanceof ApiFailure ? reason.message : "Cannot reach the NimbusOps server.");
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
    try {
      await session.logout();
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
        {session?.error && (
          <p role="alert" className="text-xs text-signal-warn">
            {session.error}
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
              The readiness probe reports {readiness?.ready === false ? "not ready" : "ready"} with database state{" "}
              {readiness?.database ?? health?.database ?? "unknown"}.
            </p>
            <div data-testid="readiness-recovery" className="space-y-1 text-xs text-ink-200">
              <p className="font-semibold">Diagnose on the server:</p>
              <ol className="list-decimal space-y-1 pl-5 text-ink-300">
                <li>Process: confirm the backend service is running (systemctl status nimbusops-backend).</li>
                <li>Database: check the database file path and permissions (NIMBOPS_DB_PATH).</li>
                <li>Logs: inspect the control-plane service logs for the failing dependency.</li>
              </ol>
              <p className="text-ink-400">This console does not restart services.</p>
            </div>
          </div>
        ) : readiness || health ? (
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
          <Fact label="Hosts online" value={readiness?.hosts_online !== undefined ? String(readiness.hosts_online) : "unknown"} />
          <Fact
            label="Operations in flight"
            value={readiness?.operations_in_flight !== undefined ? String(readiness.operations_in_flight) : "unknown"}
          />
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
          These unit paths are the deployment contract. They are not installed by NimbusOps and are not edited from this
          console; install or repair them on the server.
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
