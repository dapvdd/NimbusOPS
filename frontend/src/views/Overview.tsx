/**
 * Overview: host counts, connectivity, latest telemetry per host.
 * Reads actual backend data; every UI state is explicit.
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiFailure } from "../api/client";
import type { Host, HostListResponse } from "../api/types";
import { MetricCard } from "../components/MetricCard";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyPanel, ErrorPanel, LoadingPanel } from "../components/StatePanels";
import { ageSeconds, formatAge } from "../lib/format";

export default function Overview() {
  const [data, setData] = useState<HostListResponse | null>(null);
  const [error, setError] = useState<ApiFailure | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.listHosts();
      setData(resp);
    } catch (err) {
      setError(err as ApiFailure);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = window.setInterval(load, 30_000);
    return () => window.clearInterval(id);
  }, [load]);

  if (loading && !data) return <LoadingPanel label="Loading hosts" />;
  if (error && !data)
    return (
      <ErrorPanel
        title={error.kind === "network" ? "API unavailable" : "Failed to load hosts"}
        detail={error.message}
        onRetry={load}
      />
    );

  const hosts = data?.hosts ?? [];
  const online = hosts.filter((h) => h.status === "ONLINE").length;
  const stale = hosts.filter((h) => h.status === "STALE").length;
  const offline = hosts.filter((h) => h.status === "OFFLINE").length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Overview</h1>
        <p className="text-sm text-ink-400">Registered hosts and their latest telemetry.</p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <CountCard label="Registered" value={hosts.length} />
        <CountCard label="Online" value={online} accent="text-signal-ok" />
        <CountCard label="Stale" value={stale} accent="text-signal-warn" />
        <CountCard label="Offline" value={offline} accent="text-signal-bad" />
      </div>

      {hosts.length === 0 ? (
        <EmptyPanel
          title="No hosts registered"
          detail="Enroll a host agent to see telemetry here. See docs/DEVELOPMENT.md for the enrollment command."
        />
      ) : (
        <div className="space-y-3">
          {hosts.map((host) => (
            <HostRow key={host.id} host={host} />
          ))}
        </div>
      )}

      {error && data && (
        <p className="text-xs text-signal-warn" role="status">
          Last refresh failed ({error.message}); showing data from the previous poll.
        </p>
      )}
    </div>
  );
}

function CountCard({ label, value, accent }: { label: string; value: number; accent?: string }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-850 p-4">
      <div className="text-xs uppercase tracking-wider text-ink-300">{label}</div>
      <div className={`mt-1 font-mono text-2xl font-semibold ${accent ?? "text-ink-100"}`} data-testid={`count-${label.toLowerCase()}`}>
        {value}
      </div>
    </div>
  );
}

function HostRow({ host }: { host: Host }) {
  const age = ageSeconds(host.last_telemetry_at);
  const lm = host.latest_metrics;
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-850">
      <div className="flex flex-wrap items-center gap-3 border-b border-ink-700 px-4 py-3">
        <Link to={`/hosts/${host.id}`} className="font-medium text-ink-100 hover:text-signal-info">
          {host.hostname}
        </Link>
        <StatusBadge status={host.status} size="sm" />
        <span className="ml-auto text-xs text-ink-400">
          {age !== null ? `telemetry ${formatAge(age)}` : "no telemetry yet"}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-3 p-3 sm:grid-cols-3">
        <MetricCard label="CPU" percent={lm ? lm.cpu_percent : null} hint={host.cpu_cores ? `${host.cpu_cores} cores` : undefined} />
        <MetricCard
          label="RAM"
          percent={lm ? lm.memory_used_percent : null}
          usedBytes={lm ? lm.memory_used_bytes : null}
          totalBytes={lm ? lm.memory_total_bytes : null}
        />
        <MetricCard
          label="Disk"
          percent={lm ? lm.disk_used_percent : null}
          usedBytes={lm ? lm.disk_used_bytes : null}
          totalBytes={lm ? lm.disk_total_bytes : null}
        />
      </div>
      {host.status === "STALE" && (
        <div className="px-4 pb-3 text-xs text-signal-warn">
          Telemetry is stale — the agent has not reported recently. Values shown are old, not current.
        </div>
      )}
      {host.status === "OFFLINE" && (
        <div className="px-4 pb-3 text-xs text-signal-bad">
          Agent offline — no heartbeat within the offline threshold. Metrics are historical.
        </div>
      )}
    </div>
  );
}
