/**
 * Host detail: identity, OS info, agent status, current metrics, and a
 * bounded metric history. All values come from the API; missing → "—".
 */

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiFailure } from "../api/client";
import type { Host, HostMetricsResponse } from "../api/types";
import { MetricCard } from "../components/MetricCard";
import { StatusBadge } from "../components/StatusBadge";
import { ErrorPanel, LoadingPanel } from "../components/StatePanels";
import { ageSeconds, formatAge, formatUtcTime } from "../lib/format";

export default function HostDetail() {
  const { hostId = "" } = useParams();
  const [host, setHost] = useState<Host | null>(null);
  const [history, setHistory] = useState<HostMetricsResponse | null>(null);
  const [error, setError] = useState<ApiFailure | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [h, m] = await Promise.all([api.getHost(hostId), api.getHostMetrics(hostId, 60)]);
      setHost(h);
      setHistory(m);
    } catch (err) {
      setError(err as ApiFailure);
    } finally {
      setLoading(false);
    }
  }, [hostId]);

  useEffect(() => {
    load();
    const id = window.setInterval(load, 30_000);
    return () => window.clearInterval(id);
  }, [load]);

  if (loading && !host) return <LoadingPanel label="Loading host" />;
  if (error && !host)
    return (
      <ErrorPanel
        title={error.status === 404 ? "Host not found" : "Failed to load host"}
        detail={error.message}
        onRetry={load}
      />
    );
  if (!host) return null;

  const lm = host.latest_metrics;
  const teleAge = ageSeconds(host.last_telemetry_at);
  const seenAge = ageSeconds(host.last_seen_at);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/" className="text-sm text-ink-400 hover:text-ink-200">
          ← Overview
        </Link>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold tracking-tight">{host.hostname}</h1>
        <StatusBadge status={host.status} />
        {host.is_revoked && (
          <span className="rounded-full border border-signal-bad/40 bg-signal-bad/10 px-2 py-0.5 text-xs text-signal-bad">
            Credential revoked
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
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

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <InfoPanel title="Host">
          <InfoRow label="Host ID" value={<span className="font-mono text-xs">{host.id}</span>} />
          <InfoRow label="Platform" value={host.platform ? `${host.platform} ${host.platform_release ?? ""}` : "—"} />
          <InfoRow label="Agent version" value={host.agent_version ?? "—"} />
          <InfoRow label="Total memory" value={host.total_memory_bytes ? `${(host.total_memory_bytes / 2 ** 30).toFixed(1)} GiB` : "—"} />
        </InfoPanel>
        <InfoPanel title="Connectivity">
          <InfoRow label="Last heartbeat" value={seenAge !== null ? `${formatAge(seenAge)} (${formatUtcTime(host.last_seen_at)})` : "never"} />
          <InfoRow label="Last telemetry" value={teleAge !== null ? `${formatAge(teleAge)} (${formatUtcTime(host.last_telemetry_at)})` : "never"} />
          <InfoRow label="Enrolled at" value={formatUtcTime(host.enrolled_at)} />
          <InfoRow
            label="Agent status"
            value={
              host.status === "ONLINE"
                ? "Reporting"
                : host.status === "STALE"
                  ? "Late — telemetry may be outdated"
                  : "Not reporting"
            }
          />
        </InfoPanel>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-medium text-ink-200">Recent telemetry</h2>
        {!history || history.points.length === 0 ? (
          <p className="rounded-lg border border-dashed border-ink-600 bg-ink-900 p-6 text-center text-xs text-ink-400">
            No telemetry recorded yet.
          </p>
        ) : (
          <HistoryTable points={history.points} />
        )}
      </div>
    </div>
  );
}

function InfoPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-850 p-4">
      <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-ink-300">{title}</h3>
      <dl className="space-y-2">{children}</dl>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 text-sm">
      <dt className="text-ink-400">{label}</dt>
      <dd className="text-right text-ink-100">{value}</dd>
    </div>
  );
}

function HistoryTable({ points }: { points: { recorded_at: string; cpu_percent: number; memory_used_percent: number; disk_used_percent: number }[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-ink-700">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-ink-700 bg-ink-900 text-left text-xs uppercase tracking-wider text-ink-400">
            <th className="px-4 py-2 font-medium">Time (UTC)</th>
            <th className="px-4 py-2 font-medium">CPU</th>
            <th className="px-4 py-2 font-medium">RAM</th>
            <th className="px-4 py-2 font-medium">Disk</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.recorded_at} className="border-b border-ink-800 last:border-0 font-mono text-xs">
              <td className="px-4 py-2 text-ink-300">{formatUtcTime(p.recorded_at)}</td>
              <td className="px-4 py-2 text-ink-100">{p.cpu_percent.toFixed(1)}%</td>
              <td className="px-4 py-2 text-ink-100">{p.memory_used_percent.toFixed(1)}%</td>
              <td className="px-4 py-2 text-ink-100">{p.disk_used_percent.toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
