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
import { useAdmin } from "../auth/Session";
import HostDocker from "../components/HostDocker";

export default function HostDetail({ view = "overview" }: { view?: "overview" | "monitoring" } = {}) {
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
        {view === "overview" && (
          <Link to="/" className="text-sm text-ink-400 hover:text-ink-200">
            ← Overview
          </Link>
        )}
      </div>
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
      )}

      <HostDocker key={host.id} host={host} onChanged={() => void load()} />

      <LifecyclePanel host={host} onChanged={() => void load()} />

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

/**
 * S4-1b (Phase C): ADMIN-only credential lifecycle panel on host detail.
 *
 * Rotate: POST /hosts/{id}/rotate-credential → new token shown once + grace
 * deadline. Re-enroll: POST /hosts/{id}/re-enroll → bootstrap token shown
 * once. Both surface typed failures via role=alert; VIEWER sees nothing.
 * Tokens live in component state only — never in storage, URL, or logs.
 */
function LifecyclePanel({ host, onChanged }: { host: Host; onChanged: () => void }) {
  const admin = useAdmin();
  const [rotation, setRotation] = useState<{ token: string; graceUntil: string } | null>(null);
  const [bootstrap, setBootstrap] = useState<{ token: string; expiresAt: string } | null>(null);
  const [busy, setBusy] = useState<"" | "rotate" | "reenroll">("");
  const [error, setError] = useState("");

  if (!admin) return null;

  const rotate = async () => {
    if (busy || rotation) return;
    setBusy("rotate");
    setError("");
    try {
      const r = await api.rotateCredential(host.id);
      setRotation({ token: r.new_agent_token, graceUntil: r.old_token_expires_at });
      onChanged();
    } catch (err) {
      setError(err instanceof ApiFailure ? err.message : "Rotation failed.");
    } finally {
      setBusy("");
    }
  };

  const reenroll = async () => {
    if (busy || bootstrap) return;
    setBusy("reenroll");
    setError("");
    try {
      const r = await api.issueReenrollBootstrap(host.id);
      setBootstrap({ token: r.bootstrap_token, expiresAt: r.expires_at });
      onChanged();
    } catch (err) {
      setError(err instanceof ApiFailure ? err.message : "Re-enroll failed.");
    } finally {
      setBusy("");
    }
  };

  return (
    <section aria-label="Credential lifecycle" className="space-y-3 rounded-lg border border-ink-700 bg-ink-850 p-4">
      <h2 className="font-medium">Credential lifecycle</h2>
      <p className="text-sm text-ink-300">
        Credential version {host.credential_version ?? 1}. Rotation keeps the previous token valid for a grace
        window; re-enroll issues a single-use bootstrap for a lost/revoked credential.
      </p>
      <div className="flex flex-wrap gap-4">
        <button
          className="rounded border border-ink-600 px-3 py-2 text-sm disabled:opacity-40"
          disabled={busy !== "" || rotation !== null}
          onClick={() => void rotate()}
        >
          Rotate credential
        </button>
        <button
          className="rounded border border-ink-600 px-3 py-2 text-sm disabled:opacity-40"
          disabled={busy !== "" || bootstrap !== null}
          onClick={() => void reenroll()}
        >
          Re-enroll this host
        </button>
      </div>
      {rotation && (
        <div className="space-y-2 rounded border border-signal-info/40 bg-ink-900 p-3">
          <p className="text-xs font-semibold text-amber-300">New agent token — shown once. Copy it now.</p>
          <code className="block break-all rounded border border-ink-600 bg-ink-950 p-2 font-mono text-xs">{rotation.token}</code>
          <p data-testid="grace-deadline" className="text-xs text-ink-300">Grace ends {formatUtcTime(rotation.graceUntil)} — update the agent before then.</p>
        </div>
      )}
      {bootstrap && (
        <div className="space-y-2 rounded border border-signal-info/40 bg-ink-900 p-3">
          <p className="text-xs font-semibold text-amber-300">Bootstrap token — shown once. Copy it now.</p>
          <code className="block break-all rounded border border-ink-600 bg-ink-950 p-2 font-mono text-xs">{bootstrap.token}</code>
          <p className="text-xs text-ink-300">Expires {formatUtcTime(bootstrap.expiresAt)}.</p>
        </div>
      )}
      {error && <p role="alert" className="text-xs text-signal-bad">{error}</p>}
    </section>
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
 *
 * Reads the host's current classification, PATCHes /hosts/{id} with the new
 * value, and refetches on success. VIEWERs see the value as plain text (the
 * endpoint is ADMIN-only; hiding the control is honest — the API rejects them
 * with 403 anyway). A failed PATCH surfaces an error and keeps the selector on
 * the persisted value (no optimistic state).
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
