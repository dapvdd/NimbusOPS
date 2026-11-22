import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiFailure } from "../api/client";
import type { Host } from "../api/types";
import { useAdmin } from "../auth/Session";
import { ErrorPanel, LoadingPanel } from "../components/StatePanels";
import { StatusBadge } from "../components/StatusBadge";
import { MetricCard } from "../components/MetricCard";
import { useFleet } from "../hooks/useFleet";
import { deriveOnboardingState } from "../lib/onboarding";
import { Button } from "../ui/Button";

type FilterValue = "ALL" | "ONLINE" | "STALE" | "OFFLINE" | "REVOKED" | "AWAITING" | "PRIVATE" | "PUBLIC-CLOUD";

export default function Servers() {
  const admin = useAdmin();
  const navigate = useNavigate();
  const { hosts, tokens, loading, error, tokensError, refetch } = useFleet();

  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FilterValue>("ALL");
  const [removing, setRemoving] = useState<{ id: string; name: string } | null>(null);

  // Active tokens waiting for enrollment
  const awaitingTokens = (tokens || []).filter(
    (t) => deriveOnboardingState(t) === "WAITING"
  );

  const matches = (value: string) => value.toLowerCase().includes(query.toLowerCase());
  const hostEnv = (h: Host) => h.environment ?? "PRIVATE";

  // Filter logic
  const filteredHosts = hosts.filter((h) => {
    if (!matches(h.hostname)) return false;
    if (filter === "ALL") return true;
    if (filter === "REVOKED") return h.is_revoked || h.status === "REVOKED";
    if (filter === "AWAITING") return false;
    if (filter === "PRIVATE" || filter === "PUBLIC-CLOUD") return hostEnv(h) === filter;
    return h.status === filter && !h.is_revoked;
  });

  const filteredAwaiting = (filter === "ALL" || filter === "AWAITING")
    ? awaitingTokens.filter((t) => matches(t.hostname))
    : [];

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-widest text-signal-info">Infrastructure / Fleet</p>
          <h1 className="mt-2 text-3xl font-semibold text-ink-50">Servers</h1>
          <p className="mt-2 text-sm text-ink-300">Your infrastructure, one host at a time.</p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void refetch()}
            className="text-xs"
          >
            Refresh
          </Button>
          {admin && (
            <Button
              type="button"
              variant="primary"
              onClick={() => navigate("/servers/new")}
            >
              Add Server
            </Button>
          )}
        </div>
      </header>

      {/* Search Bar */}
      <label className="block text-sm">
        <span className="text-ink-200">Search servers</span>
        <input
          className="mt-2 block w-full rounded-lg border border-ink-600 bg-ink-900 p-3 text-ink-100 placeholder-ink-500 focus:border-signal-info focus:outline-none"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by server name…"
        />
      </label>

      {/* Filter Chips */}
      <div role="group" aria-label="Filter servers" className="flex flex-wrap gap-2">
        {(["ALL", "ONLINE", "STALE", "OFFLINE", "REVOKED", "AWAITING", "PRIVATE", "PUBLIC-CLOUD"] as const).map((v) => (
          <button
            key={v}
            type="button"
            aria-pressed={filter === v}
            onClick={() => setFilter(v)}
            className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
              filter === v
                ? "border-signal-info bg-signal-info/10 text-signal-info"
                : "border-ink-700 bg-surface-2 text-ink-300 hover:border-ink-600 hover:text-ink-200"
            }`}
          >
            {v}
          </button>
        ))}
      </div>

      {loading && <LoadingPanel label="Loading real servers" />}

      {tokensError && (
        <div role="alert" className="rounded-lg border border-signal-warn/40 p-3 text-sm text-signal-warn">
          <p>Enrollment token feed unavailable. Awaiting enrollment status is unknown.</p>
          <Button size="sm" onClick={() => void refetch()}>Retry token feed</Button>
        </div>
      )}

      {error && (
        <ErrorPanel
          error={error}
          onRetry={() => void refetch()}
        />
      )}

      {/* Fleet Table / Grid */}
      {!loading && !error && (
        <>
          <div className="flex items-center justify-between">
            <h2 className="text-xs uppercase tracking-widest text-ink-300">
              Fleet · {hosts.length} {hosts.length === 1 ? "host" : "hosts"}
              {awaitingTokens.length > 0 && ` (${awaitingTokens.length} awaiting enrollment)`}
            </h2>
          </div>

          {filteredHosts.length === 0 && filteredAwaiting.length === 0 && !(tokensError && (filter === "ALL" || filter === "AWAITING")) && (
            <p className="text-sm text-ink-400 py-8 text-center">
              {query ? "No servers match your search." : filter === "AWAITING" ? "No servers awaiting enrollment" : "No real servers registered"}
            </p>
          )}

          <div className="grid gap-4 xl:grid-cols-2">
            {/* Active Real Hosts */}
            {filteredHosts.map((h) => {
              const isRevoked = h.is_revoked || h.status === "REVOKED";
              return (
                <article
                  key={h.id}
                  className={`rounded-xl border p-5 ${
                    isRevoked
                      ? "border-signal-bad/40 bg-signal-bad/5"
                      : "border-ink-700 bg-ink-850"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <Link
                      className="font-semibold text-lg text-signal-info hover:underline"
                      to={`/servers/${h.id}`}
                    >
                      {h.hostname}
                    </Link>
                    <StatusBadge status={isRevoked ? "REVOKED" : h.status} />
                  </div>

                  <p className="my-4 text-xs text-ink-300">
                    <span
                      className={`mr-2 rounded-full border px-2 py-0.5 ${
                        isRevoked ? "border-signal-bad/40 text-signal-bad" : "border-ink-600"
                      }`}
                    >
                      {isRevoked ? "REVOKED" : "ACTIVE"}
                    </span>
                    <span className="mr-2 rounded-full border border-ink-600 px-2 py-0.5">
                      {hostEnv(h)}
                    </span>
                    REAL · {h.enrollment_status}
                    {h.docker_enabled ? " · Docker enabled" : ""}
                  </p>

                  <div className="grid grid-cols-3 gap-2">
                    <MetricCard
                      label="CPU"
                      percent={h.latest_metrics ? h.latest_metrics.cpu_percent : null}
                    />
                    <MetricCard
                      label="RAM"
                      percent={h.latest_metrics ? h.latest_metrics.memory_used_percent : null}
                    />
                    <MetricCard
                      label="Disk"
                      percent={h.latest_metrics ? h.latest_metrics.disk_used_percent : null}
                    />
                  </div>

                  {admin && (
                    <div className="mt-4 flex items-center justify-between pt-2 border-t border-ink-800">
                      {isRevoked ? (
                        <Link
                          to={`/servers/${h.id}`}
                          className="text-xs font-semibold text-signal-info hover:underline"
                        >
                          Re-enroll
                        </Link>
                      ) : (
                        <button
                          type="button"
                          className="text-xs text-signal-bad hover:underline"
                          aria-label={`Unregister ${h.hostname}`}
                          onClick={() => setRemoving({ id: h.id, name: h.hostname })}
                        >
                          Unregister
                        </button>
                      )}
                    </div>
                  )}
                </article>
              );
            })}

            {/* Awaiting Enrollment Rows */}
            {filteredAwaiting.map((t) => (
              <article
                key={t.id}
                className="rounded-xl border border-dashed border-ink-700 bg-surface-1/50 p-5"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="font-semibold text-lg text-ink-200">
                    {t.hostname}
                  </span>
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-signal-warn/30 bg-signal-warn/10 px-2.5 py-1 text-xs font-medium text-signal-warn">
                    <span className="font-mono text-xs leading-none">○</span>
                    <span>Awaiting enrollment</span>
                  </span>
                </div>
                <p className="my-4 text-xs text-ink-400">
                  Bootstrap token issued · Expires in {countdownLabel(t.expires_at)}
                </p>
                <div className="rounded-lg border border-ink-800 bg-ink-900/60 p-3 text-xs text-ink-300">
                  Not enrolled yet. Run the onboarding commands on the host to complete registration.
                </div>
              </article>
            ))}
          </div>
        </>
      )}

      {/* Safe Unregister Dialog */}
      {admin && removing && (
        <UnregisterDialog host={removing} onClose={() => setRemoving(null)} onRevoked={() => void refetch()} />
      )}
    </div>
  );
}

function countdownLabel(expiresAt: string): string {
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (ms <= 0) return "expired";
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

/** Safe Unregister: revoke-to-tombstone; requires typing the host id. */
function UnregisterDialog({
  host,
  onClose,
  onRevoked,
}: {
  host: { id: string; name: string };
  onClose: () => void;
  onRevoked: () => void;
}) {
  const [confirmText, setConfirmText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const enabled = confirmText === host.id;

  const submit = async () => {
    if (!enabled) return;
    setBusy(true);
    setError("");
    try {
      await api.revokeHost(host.id);
      onRevoked();
      onClose();
    } catch (err) {
      setError(err instanceof ApiFailure ? err.message : "Unregister failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      aria-label={`Unregister ${host.name}`}
      className="rounded-xl border border-signal-bad p-6 bg-surface-2"
    >
      <h2 className="text-xl font-semibold text-ink-50">Unregister {host.name}?</h2>
      <ul className="my-3 list-disc pl-5 text-sm text-ink-300 space-y-1">
        <li>The agent's credential is revoked: it receives 401 on its next call and stops reporting.</li>
        <li>The host becomes a tombstone: telemetry and history are retained, never deleted.</li>
        <li>Containers and files on the host are NOT removed; clean them up manually if desired.</li>
      </ul>
      <label className="block text-sm text-ink-200">
        Type the host id <span className="font-mono text-signal-bad">{host.id}</span> to confirm
        <input
          className="mt-2 block w-full max-w-sm rounded border border-ink-600 bg-ink-900 p-2 font-mono text-ink-100"
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
        />
      </label>
      {error && <p role="alert" className="mt-2 text-signal-bad text-sm">{error}</p>}
      <div className="mt-4 flex gap-4">
        <button
          type="button"
          disabled={!enabled || busy}
          className="rounded bg-signal-bad px-4 py-2 text-ink-950 font-semibold disabled:opacity-50"
          onClick={() => void submit()}
        >
          Unregister
        </button>
        <button
          type="button"
          className="text-sm text-ink-300 hover:text-ink-100"
          onClick={onClose}
        >
          Cancel
        </button>
      </div>
    </section>
  );
}
