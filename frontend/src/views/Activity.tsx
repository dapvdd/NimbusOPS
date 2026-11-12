import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Operation } from "../api/types";
import { listRemovedServers, listSimServers } from "../lib/simRegistry";
import { formatUtcTime } from "../lib/format";

const STATUSES = ["ALL", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "UNKNOWN"] as const;
type StatusFilter = (typeof STATUSES)[number];

export default function Activity({ hostId }: { hostId?: string }) {
  const [ops, setOps] = useState<Operation[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");

  const load = useCallback(() => {
    setLoading(true);
    api.listOperations(hostId ? { host_id: hostId } : {})
      .then(data => { setOps(data.operations); setError(""); })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [hostId]);

  useEffect(() => { load(); }, [load]);

  const entries = ops.filter(o => statusFilter === "ALL" || o.status === statusFilter);
  return <div className="space-y-5">
    <h1 className="text-3xl font-semibold">Activity</h1>
    <p className="text-sm text-ink-300">Operation history from the control server, oldest first.{hostId ? " Filtered to the selected host." : ""}</p>
    <div role="group" aria-label="Filter by status" className="flex flex-wrap gap-2">
      {STATUSES.map(s => (
        <button key={s} aria-pressed={statusFilter === s} onClick={() => setStatusFilter(s)}
          className={`rounded-full border px-3 py-1 text-xs ${statusFilter === s ? "border-signal-info bg-signal-info/10 text-signal-info" : "border-ink-600 text-ink-300"}`}>
          {s}
        </button>
      ))}
    </div>
    {loading && <p role="status">Loading activity…</p>}
    {error && <div role="alert" className="text-signal-bad">
      <p>{error}</p>
      <button className="mt-2 rounded-lg border border-ink-600 px-3 py-1 text-sm" onClick={load}>Retry</button>
    </div>}
    {!loading && !error && !entries.length && <p>No operations recorded for this filter.</p>}
    {entries.map(o => <article key={o.id} className="rounded-lg border border-ink-700 bg-ink-850 p-4">
      <h2 className="font-mono text-sm">{o.id}</h2>
      <p className="mt-2 font-mono text-sm">
        {o.op_type} · <span className={o.status === "FAILED" ? "text-signal-bad" : o.status === "SUCCEEDED" ? "text-signal-good" : "text-ink-300"}>{o.status}</span> · {formatUtcTime(o.updated_at)}
      </p>
      {o.error_message && <p className="mt-1 text-xs text-signal-bad">{o.error_code}: {o.error_message}</p>}
    </article>)}
    {!hostId && <section className="rounded-lg border border-amber-400/30 p-4">
      <h2 className="text-amber-300">SIMULATED · Local registry history</h2>
      {listSimServers().map(s => <p key={s.id} className="mt-3 text-sm">Added {s.name} · {formatUtcTime(s.created_at)}</p>)}
      {listRemovedServers().map((s, i) => <p key={`${s.id}-${i}`} className="mt-3 text-sm">Removed {s.name} · {formatUtcTime(s.removed_at)}</p>)}
      <p className="mt-3 text-xs text-ink-400">Browser storage only; not a durable server audit log.</p>
    </section>}
  </div>;
}
