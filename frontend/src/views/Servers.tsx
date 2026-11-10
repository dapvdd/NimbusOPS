import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Host } from "../api/types";
import { addSimServer, listSimServers, removeSimServer, type SimEnvironment } from "../lib/simRegistry";
import { StatusBadge } from "../components/StatusBadge";
import { MetricCard } from "../components/MetricCard";

export default function Servers() {
  const [hosts, setHosts] = useState<Host[]>([]);
  const [sim, setSim] = useState(listSimServers);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const [real, setReal] = useState(false);
  const [name, setName] = useState("");
  const [environment, setEnvironment] = useState<SimEnvironment>("SIMULATED-DEV");
  const [formError, setFormError] = useState("");
  const [removing, setRemoving] = useState<{ id: string; name: string } | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => api.listHosts().then(data => { if (alive) { setHosts(data.hosts); setError(""); } }).catch(e => { if (alive) setError(e.message); }).finally(() => { if (alive) setLoading(false); });
    void load();
    const timer = window.setInterval(load, 30000);
    const sync = () => setSim(listSimServers());
    window.addEventListener("nimbusops:registry", sync);
    window.addEventListener("storage", sync);
    return () => { alive = false; clearInterval(timer); window.removeEventListener("nimbusops:registry", sync); window.removeEventListener("storage", sync); };
  }, []);
  const matches = (value: string) => value.toLowerCase().includes(query.toLowerCase());
  return <div className="space-y-6">
    <header className="flex items-center justify-between gap-4"><div><p className="text-xs uppercase tracking-widest text-signal-info">Infrastructure / Fleet</p><h1 className="mt-2 text-3xl font-semibold">Servers</h1><p className="mt-2 text-sm text-ink-300">Your infrastructure, one host at a time.</p></div><button className="rounded-lg bg-signal-info px-4 py-3 text-ink-950 font-semibold" onClick={() => { setAdding(true); setFormError(""); }}>Add Server</button></header>
    <label className="block text-sm">Search servers<input className="mt-2 block w-full rounded-lg border border-ink-600 bg-ink-900 p-3" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search by server name…" /></label>
    {loading && <p role="status">Loading real servers…</p>}
    {error && <p role="alert" className="rounded-lg border border-signal-bad p-4 text-signal-bad">Real infrastructure unavailable: {error}. Simulations below are local only.</p>}
    <h2 className="text-xs uppercase tracking-widest text-ink-300">Real infrastructure · {hosts.length}</h2>
    {!loading && !error && hosts.length === 0 && <p>No real servers registered</p>}
    <div className="grid gap-4 xl:grid-cols-2">{hosts.filter(h => matches(h.hostname)).map(h => <article key={h.id} className="rounded-xl border border-ink-700 bg-ink-850 p-5"><div className="flex items-center justify-between gap-3"><Link className="font-semibold text-lg text-signal-info" to={`/hosts/${h.id}`}>{h.hostname}</Link><StatusBadge status={h.status} /></div><p className="my-4 text-xs text-ink-300">REAL · Environment unspecified</p><div className="grid grid-cols-3 gap-2"><MetricCard label="CPU" percent={h.latest_metrics?.cpu_percent ?? null} /><MetricCard label="RAM" percent={h.latest_metrics?.memory_used_percent ?? null} /><MetricCard label="Disk" percent={h.latest_metrics?.disk_used_percent ?? null} /></div><p className="mt-4 text-xs text-ink-400">Unregister: NOT IMPLEMENTED — authorization and credential revocation required.</p></article>)}</div>
    <section className="rounded-xl border border-amber-400/30 bg-amber-400/5 p-5"><h2 className="font-semibold text-amber-300">SIMULATED · Local demo registry</h2><p className="mt-2 text-sm text-ink-300">These servers are browser-only demonstrations. They have no agent or Docker access.</p><div className="mt-5 grid gap-4 xl:grid-cols-2">{sim.filter(h => matches(h.name)).map(h => <article key={h.id} className="rounded-lg border border-ink-600 bg-ink-900 p-5"><Link className="text-lg font-semibold text-signal-info" to={`/servers/${h.id}`}>{h.name}</Link><p className="my-3 text-xs text-amber-300">{h.environment} · SIMULATED ONLINE</p><p className="text-sm text-ink-300">Synthetic preview · CPU {10 + h.seed % 60}% · RAM {20 + h.seed % 50}%</p><button className="mt-4 text-sm text-signal-bad" aria-label={`Remove ${h.name}`} onClick={() => setRemoving(h)}>Remove</button></article>)}</div>{sim.length === 0 && <p className="mt-4 text-sm">No simulated servers. Add one to explore the dashboard.</p>}</section>
    {query && !hosts.some(h => matches(h.hostname)) && !sim.some(h => matches(h.name)) && <p>No servers match your search.</p>}
    {adding && <section aria-label="Add server" className="rounded-xl border border-signal-info bg-ink-850 p-6"><h2 className="text-xl font-semibold">Add server</h2><div className="my-4 flex gap-4"><button onClick={() => setReal(false)} aria-pressed={!real}>Simulated demo server</button><button onClick={() => setReal(true)} aria-pressed={real}>Existing server</button></div>{real ? <p>NOT IMPLEMENTED — secure enrollment requires authorized, one-time expiring tokens. No credentials are generated here.</p> : <form className="space-y-4" onSubmit={e => { e.preventDefault(); try { addSimServer(name, environment); setAdding(false); setName(""); } catch (err) { setFormError((err as Error).message); } }}><label className="block">Server name<input autoFocus className="ml-3 rounded border border-ink-600 bg-ink-900 p-2" value={name} onChange={e => setName(e.target.value)} maxLength={64} /></label><label className="block">Environment<select className="ml-3 rounded bg-ink-900 p-2" value={environment} onChange={e => setEnvironment(e.target.value as SimEnvironment)}>{["SIMULATED-DEV", "SIMULATED-STAGING", "SIMULATED-PROD"].map(v => <option key={v}>{v}</option>)}</select></label>{formError && <p role="alert">{formError}</p>}<button className="rounded bg-signal-info px-4 py-2 text-ink-950">Create simulated server</button></form>}<button className="mt-4 text-ink-300" onClick={() => setAdding(false)}>Cancel</button></section>}
    {removing && <section aria-label="Confirm server removal" className="rounded-xl border border-signal-bad p-6"><h2>Remove {removing.name}?</h2><p className="my-3 text-sm">This removes only the browser simulation. Local removal history is retained.</p><button className="mr-6 text-signal-bad" onClick={() => { try { removeSimServer(removing.id); setRemoving(null); } catch (err) { setError((err as Error).message); } }}>Confirm removal</button><button onClick={() => setRemoving(null)}>Cancel</button></section>}
  </div>;
}
