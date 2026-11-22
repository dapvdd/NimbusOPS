/**
 * Overview dashboard: KPI counts, the explicit "needs attention" queue, a
 * compact fleet table, and the last few real operations.
 *
 * Every value is the control plane's own state: host lifecycle comes from
 * `/hosts`, awaiting enrollment from live bootstrap tokens, control-plane
 * health from `/health`, and recent work from `/operations`. Nothing here is
 * simulated, and the "all clear" banner only appears when `/health` is ok AND
 * nothing needs attention.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiFailure } from "../api/client";
import type {
  BootstrapTokenInfo,
  HealthResponse,
  Host,
  HostListResponse,
  Operation,
} from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyPanel, ErrorPanel, LoadingPanel } from "../components/StatePanels";
import {
  ageSeconds,
  formatAge,
  formatPercent,
  formatUtcTime,
} from "../lib/format";

const ATTENTION_WINDOW_MS = 5 * 60_000;

interface AttentionItem {
  key: string;
  hostname: string | null;
  label: string;
  detail: string;
  href: string;
  tone: "bad" | "warn";
}

function effectiveStatus(host: Host): Host["status"] {
  if (host.is_revoked || host.enrollment_status === "REVOKED") return "REVOKED";
  return host.status;
}

function isLiveToken(token: BootstrapTokenInfo, now: number): boolean {
  if (token.consumed_at || token.revoked_at) return false;
  return new Date(token.expires_at).getTime() > now;
}

function attentionRank(host: Host): number {
  const status = effectiveStatus(host);
  if (status === "REVOKED") return 0;
  if (status === "OFFLINE") return 1;
  if (status === "STALE") return 2;
  if (host.docker_enabled && host.agent_mode !== "executor") return 3;
  return 4;
}

export default function Overview() {
  const [hosts, setHosts] = useState<HostListResponse | null>(null);
  const [tokens, setTokens] = useState<BootstrapTokenInfo[]>([]);
  const [operations, setOperations] = useState<Operation[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  // Availability of each feed. A feed that could not be read (e.g. the ADMIN-only
  // token list behind a VIEWER session) must render as "unknown", never as an
  // authoritative zero.
  const [availability, setAvailability] = useState({ tokens: true, operations: true, health: true });
  const [error, setError] = useState<ApiFailure | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);

    const [hostsResult, tokensResult, opsResult, healthResult] = await Promise.allSettled([
      api.listHosts(),
      api.listBootstrapTokens({ limit: 50 }),
      api.listOperations({ limit: 5 }),
      api.health(),
    ]);

    if (hostsResult.status === "fulfilled") {
      setHosts(hostsResult.value);
    } else {
      setError(hostsResult.reason as ApiFailure);
    }
    if (tokensResult.status === "fulfilled") {
      setTokens(tokensResult.value?.tokens ?? []);
      setAvailability((prev) => ({ ...prev, tokens: true }));
    } else {
      setAvailability((prev) => ({ ...prev, tokens: false }));
    }
    if (opsResult.status === "fulfilled") {
      setOperations(opsResult.value?.operations ?? []);
      setAvailability((prev) => ({ ...prev, operations: true }));
    } else {
      setAvailability((prev) => ({ ...prev, operations: false }));
    }
    if (healthResult.status === "fulfilled") {
      setHealth(healthResult.value ?? null);
      setAvailability((prev) => ({ ...prev, health: true }));
    } else {
      setAvailability((prev) => ({ ...prev, health: false }));
    }

    setLastUpdatedAt(Date.now());
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    const id = window.setInterval(load, 30_000);
    return () => window.clearInterval(id);
  }, [load]);

  const hostList = useMemo(() => hosts?.hosts ?? [], [hosts]);

  const attention = useMemo(() => {
    const now = Date.now();
    const items: AttentionItem[] = [];

    const sorted = [...hostList].sort((a, b) => {
      const rank = attentionRank(a) - attentionRank(b);
      return rank !== 0 ? rank : a.hostname.localeCompare(b.hostname);
    });

    for (const host of sorted) {
      const status = effectiveStatus(host);
      if (status === "REVOKED") {
        items.push({
          key: `revoked-${host.id}`,
          hostname: host.hostname,
          label: "Credential revoked",
          detail: "Re-enroll required — the old credential is permanently refused.",
          href: `/servers/${host.id}`,
          tone: "bad",
        });
      } else if (status === "OFFLINE") {
        items.push({
          key: `offline-${host.id}`,
          hostname: host.hostname,
          label: "Host unreachable",
          detail: "No heartbeat within the offline threshold.",
          href: `/servers/${host.id}`,
          tone: "warn",
        });
      } else if (status === "STALE") {
        items.push({
          key: `stale-${host.id}`,
          hostname: host.hostname,
          label: "Reporting gap",
          detail: "The agent has not reported recently; shown values are old.",
          href: `/servers/${host.id}`,
          tone: "warn",
        });
      } else if (host.docker_enabled && host.agent_mode !== "executor") {
        items.push({
          key: `docker-${host.id}`,
          hostname: host.hostname,
          label: "Docker unavailable",
          detail: `Docker is enabled but the agent reports ${host.agent_mode ?? "no mode"}; containers will not start.`,
          href: `/servers/${host.id}`,
          tone: "warn",
        });
      }
    }

    for (const token of tokens) {
      if (token.consumed_at || token.revoked_at) continue;
      const expiresAt = new Date(token.expires_at).getTime();
      if (expiresAt <= now) {
        items.push({
          key: `token-expired-${token.id}`,
          hostname: token.hostname,
          label: "Enrollment token expired",
          detail: `Expired ${formatUtcTime(token.expires_at)}; issue a new token.`,
          href: "/servers/new",
          tone: "warn",
        });
      } else if (expiresAt - now < ATTENTION_WINDOW_MS) {
        items.push({
          key: `token-expiring-${token.id}`,
          hostname: token.hostname,
          label: "Enrollment token expiring",
          detail: `Expires ${formatUtcTime(token.expires_at)} — finish enrolling before then.`,
          href: "/servers/new",
          tone: "warn",
        });
      }
    }

    if (health && (health.status !== "ok" || health.database !== "ok")) {
      items.push({
        key: "control-plane-degraded",
        hostname: null,
        label: "Control plane degraded",
        detail: `Database state: ${health.database ?? "unknown"}. Check the control-plane health details.`,
        href: "/settings",
        tone: "bad",
      });
    }

    return items;
  }, [hostList, tokens, health]);

  if (loading && !hosts) return <LoadingPanel label="Loading hosts" />;
  if (error && !hosts)
    return (
      <ErrorPanel
        title={error.kind === "network" ? "API unavailable" : "Failed to load hosts"}
        detail={error.message}
        onRetry={load}
      />
    );

  const now = Date.now();
  const counts = {
    revoked: 0,
    online: 0,
    stale: 0,
    offline: 0,
  };
  for (const host of hostList) {
    const status = effectiveStatus(host);
    if (status === "REVOKED") counts.revoked += 1;
    else if (status === "ONLINE") counts.online += 1;
    else if (status === "STALE") counts.stale += 1;
    else if (status === "OFFLINE") counts.offline += 1;
  }
  const awaiting = availability.tokens ? tokens.filter((token) => isLiveToken(token, now)).length : null;
  const allClear =
    !error && !loading &&
    hostList.length > 0 &&
    attention.length === 0 &&
    availability.tokens &&
    availability.operations &&
    availability.health &&
    health?.status === "ok" &&
    health.database === "ok";

  const fleet = [...hostList].sort((a, b) => {
    const rank = attentionRank(a) - attentionRank(b);
    return rank !== 0 ? rank : a.hostname.localeCompare(b.hostname);
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Overview</h1>
        <p className="text-sm text-ink-400">
          Fleet state, what needs attention, and the latest real operations.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <CountCard label="Registered" value={hostList.length} />
        <CountCard label="Online" value={counts.online} accent="text-signal-ok" />
        <CountCard label="Stale" value={counts.stale} accent="text-signal-warn" />
        <CountCard label="Offline" value={counts.offline} accent="text-signal-bad" />
        <CountCard label="Revoked" value={counts.revoked} accent="text-purple-300" />
        <CountCard
          label="Awaiting"
          value={awaiting}
          hint={awaiting === null ? "token list unavailable" : undefined}
          accent="text-signal-info"
        />
      </div>

      {(lastUpdatedAt !== null || error) && (
        <p className="text-xs text-ink-500" data-testid="refresh-status">
          {error
            ? `Last refresh failed (${error.message}); showing data from the previous poll.`
            : lastUpdatedAt !== null
              ? `Updated ${formatUtcTime(new Date(lastUpdatedAt).toISOString())} · polls every 30s`
              : null}
        </p>
      )}

      {allClear && (
        <div
          data-testid="all-clear"
          role="status"
          className="rounded-lg border border-signal-good/40 bg-signal-good/10 p-4 text-sm text-signal-good"
        >
          All systems operational — the control plane is healthy and no host needs attention.
        </div>
      )}

      <section aria-labelledby="needs-attention-title" className="space-y-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 id="needs-attention-title" className="text-sm font-semibold uppercase tracking-wider text-ink-300">
            Needs attention
          </h2>
          <span data-testid="attention-count" className="font-mono text-xs text-ink-400">
            {attention.length}
          </span>
        </div>

        {attention.length === 0 ? (
          <div className="rounded-lg border border-ink-700 bg-ink-850 p-4 text-sm text-ink-400">
            Nothing needs attention right now.
          </div>
        ) : (
          <ul data-testid="needs-attention" className="divide-y divide-ink-800 rounded-lg border border-ink-700 bg-ink-850">
            {attention.map((item) => (
              <li key={item.key} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      aria-hidden="true"
                      className={`h-2 w-2 rounded-full ${item.tone === "bad" ? "bg-signal-bad" : "bg-signal-warn"}`}
                    />
                    <span className="font-medium text-ink-100">{item.label}</span>
                    {item.hostname && <span className="truncate font-mono text-xs text-ink-300">{item.hostname}</span>}
                  </div>
                  <p className="mt-1 text-xs text-ink-400">{item.detail}</p>
                </div>
                <Link to={item.href} className="text-xs font-medium text-signal-info hover:underline">
                  Resolve
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="fleet-title" className="space-y-3">
        <h2 id="fleet-title" className="text-sm font-semibold uppercase tracking-wider text-ink-300">
          Fleet
        </h2>

        {hostList.length === 0 ? (
          <EmptyPanel
            title="No hosts registered"
            detail="Enroll a host agent to see telemetry here. See docs/DEVELOPMENT.md for the enrollment command."
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-ink-700 bg-ink-850">
            <table className="w-full min-w-[720px] text-sm" data-testid="fleet-table">
              <thead>
                <tr className="border-b border-ink-700 text-left text-[11px] uppercase tracking-wider text-ink-400">
                  <th className="px-4 py-2 font-medium">Host</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Telemetry</th>
                  <th className="px-4 py-2 font-medium">CPU</th>
                  <th className="px-4 py-2 font-medium">RAM</th>
                  <th className="px-4 py-2 font-medium">Disk</th>
                </tr>
              </thead>
              <tbody>
                {fleet.map((host) => (
                  <FleetRow key={host.id} host={host} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section
        data-testid="recent-operations"
        aria-labelledby="recent-operations-title"
        className="space-y-3 rounded-lg border border-ink-700 bg-ink-850 p-4"
      >
        <div className="flex items-baseline justify-between gap-3">
          <h2 id="recent-operations-title" className="text-sm font-semibold uppercase tracking-wider text-ink-300">
            Recent operations
          </h2>
          <Link to="/activity" className="text-xs font-medium text-signal-info hover:underline">
            View activity
          </Link>
        </div>

        {!availability.operations ? (
          <p className="text-sm text-signal-warn" role="status">
            Operation history could not be read (requires an ADMIN session); nothing is inferred.
          </p>
        ) : operations.length === 0 ? (
          <p className="text-sm text-ink-400">No operations recorded yet.</p>
        ) : (
          <ul className="divide-y divide-ink-800">
            {operations.slice(0, 5).map((op) => (
              <li key={op.id} className="flex flex-wrap items-center gap-3 py-2 text-xs">
                <span className="font-mono text-ink-400">{formatUtcTime(op.created_at)}</span>
                <span className="font-mono font-semibold text-ink-100">{op.op_type}</span>
                <span
                  className={`font-mono ${
                    op.status === "FAILED"
                      ? "text-signal-bad"
                      : op.status === "SUCCEEDED"
                        ? "text-signal-good"
                        : "text-ink-300"
                  }`}
                >
                  {op.status}
                </span>
                {op.error_code && <span className="font-mono text-signal-bad">{op.error_code}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>

      {error && hosts && (
        <p className="text-xs text-signal-warn" role="status">
          Last refresh failed ({error.message}); showing data from the previous poll.
        </p>
      )}
    </div>
  );
}

function CountCard({
  label,
  value,
  accent,
  hint,
}: {
  label: string;
  value: number | null;
  accent?: string;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-850 p-4">
      <div className="text-xs uppercase tracking-wider text-ink-300">{label}</div>
      <div
        className={`mt-1 font-mono text-2xl font-semibold ${accent ?? "text-ink-100"}`}
        data-testid={`count-${label.toLowerCase()}`}
        title={hint}
      >
        {value === null ? "—" : value}
      </div>
      {hint && value === null && <div className="mt-0.5 text-[11px] text-ink-400">{hint}</div>}
    </div>
  );
}

function FleetRow({ host }: { host: Host }) {
  const status = effectiveStatus(host);
  const age = ageSeconds(host.last_telemetry_at);
  const lm = host.latest_metrics;

  return (
    <tr className="border-b border-ink-800 last:border-0 align-top" data-testid="fleet-row">
      <td className="px-4 py-3">
        <Link to={`/servers/${host.id}`} className="font-medium text-ink-100 hover:text-signal-info">
          {host.hostname}
        </Link>
        <div className="mt-0.5 font-mono text-[11px] text-ink-500">{host.agent_version ?? "version unknown"}</div>
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={status} size="sm" />
      </td>
      <td className="px-4 py-3 text-xs">
        {status === "REVOKED" ? (
          <span className="text-purple-300">Credential revoked — re-enroll required</span>
        ) : status === "STALE" ? (
          <span className="text-signal-warn">
            Telemetry is stale{age !== null ? ` · last seen ${formatAge(age)}` : ""}
          </span>
        ) : status === "OFFLINE" ? (
          <span className="text-signal-bad">Agent offline — no heartbeat within the offline threshold</span>
        ) : age !== null ? (
          <span className="text-ink-300">telemetry {formatAge(age)}</span>
        ) : (
          <span className="text-ink-400">no telemetry yet</span>
        )}
      </td>
      <MetricCell label="CPU" percent={lm ? lm.cpu_percent : null} />
      <MetricCell
        label="RAM"
        percent={lm ? lm.memory_used_percent : null}
        usedBytes={lm ? lm.memory_used_bytes : null}
        totalBytes={lm ? lm.memory_total_bytes : null}
      />
      <MetricCell
        label="Disk"
        percent={lm ? lm.disk_used_percent : null}
        usedBytes={lm ? lm.disk_used_bytes : null}
        totalBytes={lm ? lm.disk_total_bytes : null}
      />
    </tr>
  );
}

function MetricCell({
  label,
  percent,
  usedBytes,
  totalBytes,
}: {
  label: string;
  percent?: number | null;
  usedBytes?: number | null;
  totalBytes?: number | null;
}) {
  const hasData = percent !== null && percent !== undefined && Number.isFinite(percent);
  return (
    <td className="px-4 py-3">
      <div className="text-[11px] uppercase tracking-wider text-ink-400">{label}</div>
      <div className="font-mono text-sm font-semibold text-ink-100" data-testid="metric-value">
        {formatPercent(percent)}
      </div>
      {!hasData && <div className="mt-0.5 text-[11px] text-ink-400">No telemetry received</div>}
      {hasData && usedBytes !== undefined && usedBytes !== null && totalBytes ? (
        <div className="mt-0.5 font-mono text-[11px] text-ink-400">
          {formatBytesCompact(usedBytes)} / {formatBytesCompact(totalBytes)}
        </div>
      ) : null}
    </td>
  );
}

/** Local byte formatter keeps the table narrow; values stay exact below 10 GiB. */
function formatBytesCompact(bytes: number): string {
  const gb = bytes / 1024 ** 3;
  if (gb >= 10) return `${gb.toFixed(0)} GiB`;
  if (gb >= 1) return `${gb.toFixed(1)} GiB`;
  return `${Math.round(bytes / 1024 ** 2)} MiB`;
}
