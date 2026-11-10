import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ManagedApp } from "../api/types";
import { listRemovedServers, listSimServers } from "../lib/simRegistry";
import { formatUtcTime } from "../lib/format";
export default function Activity({ hostId }: { hostId?: string }) {
  const [apps, setApps] = useState<ManagedApp[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    api.listApplications().then(data => { if (alive) setApps(data.applications); }).catch(err => { if (alive) setError(err.message); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [hostId]);
  const entries = apps.filter(a => (!hostId || a.host_id === hostId) && a.last_operation);
  return <div className="space-y-5"><h1 className="text-3xl font-semibold">Activity</h1><p className="text-sm text-ink-300">Latest operation per deployment, from the backend. This is not a complete audit history.</p>{loading && <p role="status">Loading activity…</p>}{error && <p role="alert" className="text-signal-bad">{error}</p>}{!loading && !error && !entries.length && <p>No deployment operations available.</p>}{entries.map(a => <article key={a.deployment_id} className="rounded-lg border border-ink-700 bg-ink-850 p-4"><h2>{a.container_name}</h2><p className="mt-2 font-mono text-sm">{a.last_operation!.op_type} · {a.last_operation!.status} · {formatUtcTime(a.last_operation!.updated_at)}</p></article>)}{!hostId && <section className="rounded-lg border border-amber-400/30 p-4"><h2 className="text-amber-300">SIMULATED · Local registry history</h2>{listSimServers().map(s => <p key={s.id} className="mt-3 text-sm">Added {s.name} · {formatUtcTime(s.created_at)}</p>)}{listRemovedServers().map((s, i) => <p key={`${s.id}-${i}`} className="mt-3 text-sm">Removed {s.name} · {formatUtcTime(s.removed_at)}</p>)}<p className="mt-3 text-xs text-ink-400">Browser storage only; not a durable server audit log.</p></section>}</div>;
}
