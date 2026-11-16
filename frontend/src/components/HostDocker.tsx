import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Host, HostInventory } from "../api/types";
import { formatUtcTime } from "../lib/format";
import { useAdmin } from '../auth/Session';

export default function HostDocker({ host, onChanged }: { host: Host; onChanged: () => void }) {
  const admin = useAdmin();
  const [inventory, setInventory] = useState<HostInventory | null>(null);
  const [inventoryError, setInventoryError] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const snapshot = await api.getHostInventory(host.id);
        if (snapshot.host_id !== host.id || !Array.isArray(snapshot.containers)) throw new Error("Invalid inventory response");
        if (alive) { setInventory(snapshot); setInventoryError(""); }
      } catch (e) {
        if (alive) { setInventory(null); setInventoryError(e instanceof Error ? e.message : "Request failed"); }
      }
    };
    void load();
    const timer = window.setInterval(load, 15_000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [host.id]);
  const enable = async () => {
    if (!confirmed || busy || host.is_revoked) return;
    setBusy(true); setError("");
    try { await api.patchHost(host.id, { docker_enabled: true }); setConfirmed(false); onChanged(); }
    catch (e) { setError(e instanceof Error ? e.message : "Authorization update failed"); }
    finally { setBusy(false); }
  };
  return <section className="space-y-3 rounded-lg border border-ink-700 bg-ink-850 p-4" aria-label="Host Docker">
    <h2 className="font-medium">Docker · {host.hostname}</h2>
    <p className="font-mono text-xs">Target host: {host.id}</p>
    <p>{host.docker_enabled ? "Docker operations enabled" : "Docker operations disabled"}</p>
    {!host.docker_enabled && admin && <>
      <p className="text-sm text-ink-300">Requires an authenticated ADMIN session. Enable only after the owner approves disposable Docker operations on this exact host. This does not install Docker or start the agent.</p>
      <label className="block text-sm"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} /> Owner explicitly authorized disposable Docker operations on {host.hostname} ({host.id})</label>
      <button disabled={!confirmed || busy || host.is_revoked} onClick={() => void enable()} className="rounded border border-ink-600 px-3 py-2 disabled:opacity-40">Enable Docker for this host</button>
    </>}
    {error && <p role="alert">{error}</p>}
    <Link className="block text-signal-info" to={`/hosts/${encodeURIComponent(host.id)}?tab=Deployments`}>Open this host's deployments</Link>
    <h3 className="text-sm font-medium">Docker inventory</h3>
    {inventoryError ? <p role="status">Docker inventory unavailable: {inventoryError}. Telemetry-only agents do not report Docker inventory.</p> : !inventory ? <p>Loading Docker inventory…</p> : <>
      <p className="text-xs text-ink-300">Snapshot observed {formatUtcTime(inventory.observed_at)} · {inventory.age_seconds ?? "unknown"} seconds old at fetch; not a live probe. Host status: {host.status}.</p>
      {inventory.containers.length === 0 ? <p>No containers in this snapshot.</p> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th>Name</th><th>Image</th><th>State</th><th>Ownership</th></tr></thead><tbody>{inventory.containers.map(c => <tr key={c.id}><td>{c.names}</td><td>{c.image}</td><td>{c.state}</td><td>{c.managed ? "NimbusOps managed" : "Unmanaged"}</td></tr>)}</tbody></table></div>}
    </>}
  </section>;
}
