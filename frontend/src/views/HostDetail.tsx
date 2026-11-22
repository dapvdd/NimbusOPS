/**
 * Host detail: identity, OS info, agent status, runtime info, current metrics,
 * events history, and bounded metric history.
 * All values come from the API; missing → "—".
 */

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiFailure } from "../api/client";
import type { Host, HostEventOut, HostMetricsResponse } from "../api/types";
import { MetricCard } from "../components/MetricCard";
import { StatusBadge } from "../components/StatusBadge";
import { ErrorPanel, LoadingPanel } from "../components/StatePanels";
import { ageSeconds, formatAge, formatUtcTime } from "../lib/format";
import { useAdmin } from "../auth/Session";
import HostDocker from "../components/HostDocker";
import HostActions from "./host/HostActions";

export default function HostDetail({ view = "overview" }: { view?: "overview" | "monitoring" } = {}) {
  const { hostId = "" } = useParams();
  const [host, setHost] = useState<Host | null>(null);
  const [history, setHistory] = useState<HostMetricsResponse | null>(null);
  const [events, setEvents] = useState<HostEventOut[]>([]);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const [error, setError] = useState<ApiFailure | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [h, m, evRes] = await Promise.all([
        api.getHost(hostId),
        api.getHostMetrics(hostId, 60),
        api.listHostEvents(hostId, 50).then((result) => {
          setEventsError(null);
          return result;
        }).catch((err) => {
          setEventsError(err instanceof ApiFailure ? err.message : "Unable to load events.");
          return { events: [], count: 0 };
        }),
      ]);
      setHost(h);
      setHistory(m);
      setEvents(evRes.events || []);
    } catch (err) {
      setError(err as ApiFailure);
    } finally {
      setLoading(false);
    }
  }, [hostId]);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 30_000);
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
        {view === "overview" && (
          <Link to="/" className="text-sm text-ink-400 hover:text-ink-200">
            ← Overview
          </Link>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-lg font-semibold tracking-tight">{host.hostname}</h1>
          <StatusBadge status={host.status} />
          <EnvironmentSelector host={host} onChanged={() => void load()} />
          {host.is_revoked && (
            <span className="rounded-full border border-signal-bad/40 bg-signal-bad/10 px-2 py-0.5 text-xs text-signal-bad">
              Credential revoked
            </span>
          )}
        </div>
        <HostActions host={host} onRefresh={() => void load()} />
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

      {view === "overview" && (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
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
                host.is_revoked || host.status === "REVOKED"
                  ? "Credential revoked — re-enroll required"
                  : host.status === "ONLINE"
                    ? "Reporting"
                    : host.status === "STALE"
                      ? "Late — telemetry may be outdated"
                      : "Not reporting"
              }
            />
          </InfoPanel>
          <InfoPanel title="Runtime">
            <InfoRow
              label="Agent mode"
              value={host.agent_mode ?? "not reported"}
            />
            <InfoRow
              label="Docker permission"
              value={host.docker_enabled ? "Enabled" : "Disabled"}
            />
            <InfoRow
              label="Credential version"
              value={host.credential_version ?? 1}
            />
            {host.credential_grace_until && (
              <InfoRow
                label="Grace deadline"
                value={
                  <span data-testid="runtime-grace-deadline">
                    {formatUtcTime(host.credential_grace_until)}
                  </span>
                }
              />
            )}
            <InfoRow
              label="Next action"
              value={
                host.is_revoked || host.status === "REVOKED"
                  ? "Re-enroll required"
                  : "Normal"
              }
            />
          </InfoPanel>
        </div>
      )}

      <HostDocker key={host.id} host={host} onChanged={() => void load()} />

      {/* Host Events Section */}
      <section aria-label="Host events" className="space-y-3">
        <h2 className="text-sm font-medium text-ink-200">Host events</h2>
        {eventsError && (
          <p className="rounded border border-signal-bad/40 bg-signal-bad/10 p-2 text-xs text-signal-bad">
            {eventsError}
            <button type="button" onClick={() => void load()} className="ml-3 underline">Retry events</button>
          </p>
        )}
        {events.length === 0 ? !eventsError && (
          <p className="rounded-lg border border-dashed border-ink-600 bg-ink-900 p-6 text-center text-xs text-ink-400">
            No events yet
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-ink-700">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-ink-700 bg-ink-900 text-left text-xs uppercase tracking-wider text-ink-400">
                  <th className="px-4 py-2 font-medium">Time (UTC)</th>
                  <th className="px-4 py-2 font-medium">Event</th>
                  <th className="px-4 py-2 font-medium">Actor</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev, i) => (
                  <tr
                    key={ev.id ?? i}
                    data-testid="host-event-item"
                    className="border-b border-ink-800 last:border-0 font-mono text-xs"
                  >
                    <td className="px-4 py-2 text-ink-300">{formatUtcTime(ev.created_at)}</td>
                    <td className="px-4 py-2 font-semibold text-ink-100">{ev.event}</td>
                    <td className="px-4 py-2 text-ink-300">{ev.actor ?? "system"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

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

/**
 * S4-3 (Phase B, frontend slice): ADMIN-only environment selector.
 */
function EnvironmentSelector({ host, onChanged }: { host: Host; onChanged: () => void }) {
  const admin = useAdmin();
  const [value, setValue] = useState<"PRIVATE" | "PUBLIC-CLOUD">(host.environment);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setValue(host.environment);
  }, [host.environment]);

  if (!admin) {
    return <span className="rounded-full border border-ink-600 px-2 py-0.5 text-xs text-ink-300">{host.environment}</span>;
  }

  const change = async (next: "PRIVATE" | "PUBLIC-CLOUD") => {
    const previous = value;
    setValue(next);
    setBusy(true);
    setError("");
    try {
      await api.patchHost(host.id, { environment: next });
      onChanged();
    } catch (err) {
      setValue(previous); // Revert to the persisted value on failure.
      setError(err instanceof ApiFailure ? err.message : "Environment update failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <label className="flex items-center gap-2 text-xs text-ink-300">
      Environment
      <select
        aria-label="Environment"
        className="rounded border border-ink-600 bg-ink-900 p-1.5 text-xs text-ink-100"
        value={value}
        disabled={busy || host.is_revoked}
        onChange={(e) => void change(e.target.value as "PRIVATE" | "PUBLIC-CLOUD")}
      >
        <option value="PRIVATE">PRIVATE</option>
        <option value="PUBLIC-CLOUD">PUBLIC-CLOUD</option>
      </select>
      {error && <span role="alert" className="text-signal-bad">{error}</span>}
    </label>
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
