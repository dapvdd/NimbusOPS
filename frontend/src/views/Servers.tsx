/**
 * Servers view: real fleet + simulated registry.
 *
 * Phase 3B (Task 7): "Existing server" enrolls via operator login + a
 * single-use bootstrap token (shown once, copy + expiry countdown). Real
 * hosts expose Safe Unregister (revoke-to-tombstone) requiring typed host id.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiFailure } from "../api/client";
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
    <div className="grid gap-4 xl:grid-cols-2">{hosts.filter(h => matches(h.hostname)).map(h => <article key={h.id} className="rounded-xl border border-ink-700 bg-ink-850 p-5"><div className="flex items-center justify-between gap-3"><Link className="font-semibold text-lg text-signal-info" to={`/hosts/${h.id}`}>{h.hostname}</Link><StatusBadge status={h.status} /></div><p className="my-4 text-xs text-ink-300">REAL · {h.enrollment_status}{h.docker_enabled ? " · Docker enabled" : ""}</p><div className="grid grid-cols-3 gap-2"><MetricCard label="CPU" percent={h.latest_metrics?.cpu_percent ?? null} /><MetricCard label="RAM" percent={h.latest_metrics?.memory_used_percent ?? null} /><MetricCard label="Disk" percent={h.latest_metrics?.disk_used_percent ?? null} /></div><button className="mt-4 text-sm text-signal-bad" aria-label={`Unregister ${h.hostname}`} onClick={() => setRemoving({ id: h.id, name: h.hostname })}>Unregister</button></article>)}</div>
    <section className="rounded-xl border border-amber-400/30 bg-amber-400/5 p-5"><h2 className="font-semibold text-amber-300">SIMULATED · Local demo registry</h2><p className="mt-2 text-sm text-ink-300">These servers are browser-only demonstrations. They have no agent or Docker access.</p><div className="mt-5 grid gap-4 xl:grid-cols-2">{sim.filter(h => matches(h.name)).map(h => <article key={h.id} className="rounded-lg border border-ink-600 bg-ink-900 p-5"><Link className="text-lg font-semibold text-signal-info" to={`/servers/${h.id}`}>{h.name}</Link><p className="my-3 text-xs text-amber-300">{h.environment} · SIMULATED ONLINE</p><p className="text-sm text-ink-300">Synthetic preview · CPU {10 + h.seed % 60}% · RAM {20 + h.seed % 50}%</p><button className="mt-4 text-sm text-signal-bad" aria-label={`Remove ${h.name}`} onClick={() => setRemoving(h)}>Remove</button></article>)}</div>{sim.length === 0 && <p className="mt-4 text-sm">No simulated servers. Add one to explore the dashboard.</p>}</section>
    {query && !hosts.some(h => matches(h.hostname)) && !sim.some(h => matches(h.name)) && <p>No servers match your search.</p>}
    {adding && <section aria-label="Add server" className="rounded-xl border border-signal-info bg-ink-850 p-6"><h2 className="text-xl font-semibold">Add server</h2><div className="my-4 flex gap-4"><button onClick={() => setReal(false)} aria-pressed={!real}>Simulated demo server</button><button onClick={() => setReal(true)} aria-pressed={real}>Existing server</button></div>{real ? <EnrollFlow onDone={() => { setAdding(false); setReal(false); }} /> : <form className="space-y-4" onSubmit={e => { e.preventDefault(); try { addSimServer(name, environment); setAdding(false); setName(""); } catch (err) { setFormError((err as Error).message); } }}><label className="block">Server name<input autoFocus className="ml-3 rounded border border-ink-600 bg-ink-900 p-2" value={name} onChange={e => setName(e.target.value)} maxLength={64} /></label><label className="block">Environment<select className="ml-3 rounded bg-ink-900 p-2" value={environment} onChange={e => setEnvironment(e.target.value as SimEnvironment)}>{["SIMULATED-DEV", "SIMULATED-STAGING", "SIMULATED-PROD"].map(v => <option key={v}>{v}</option>)}</select></label>{formError && <p role="alert">{formError}</p>}<button className="rounded bg-signal-info px-4 py-2 text-ink-950">Create simulated server</button></form>}<button className="mt-4 text-ink-300" onClick={() => setAdding(false)}>Cancel</button></section>}
    {removing && (removing.id.startsWith("sim-")
      ? <section aria-label="Confirm server removal" className="rounded-xl border border-signal-bad p-6"><h2>Remove {removing.name}?</h2><p className="my-3 text-sm">This removes only the browser simulation. Local removal history is retained.</p><button className="mr-6 text-signal-bad" onClick={() => { try { removeSimServer(removing.id); setRemoving(null); } catch (err) { setError((err as Error).message); } }}>Confirm removal</button><button onClick={() => setRemoving(null)}>Cancel</button></section>
      : <UnregisterDialog host={removing} onClose={() => setRemoving(null)} />)}
  </div>;
}

/** Operator login → issue single-use bootstrap token (shown once). */
function EnrollFlow({ onDone }: { onDone: () => void }) {
  const [loggedIn, setLoggedIn] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [hostname, setHostname] = useState("");
  const [authError, setAuthError] = useState("");
  const [issueError, setIssueError] = useState("");
  const [issued, setIssued] = useState<{ token: string; expiresAt: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const submitLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setAuthError("");
    try {
      await api.login(username, password);
      setLoggedIn(true);
    } catch (err) {
      setAuthError(err instanceof ApiFailure ? err.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  };

  const issue = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setIssueError("");
    setCopied(false);
    try {
      const t = await api.issueBootstrapToken(hostname);
      setIssued({ token: t.token, expiresAt: t.expires_at });
    } catch (err) {
      setIssueError(err instanceof ApiFailure ? err.message : "Token issuance failed.");
    } finally {
      setBusy(false);
    }
  };

  if (issued) {
    return <div className="mt-4 space-y-4">
      <p className="font-semibold text-amber-300">Bootstrap token — shown once. Copy it now; it will never be shown again.</p>
      <code className="block break-all rounded-lg border border-ink-600 bg-ink-900 p-3 font-mono text-sm">{issued.token}</code>
      <p data-testid="countdown">Expires in {countdownLabel(issued.expiresAt)}</p>
      <button className="rounded bg-signal-info px-4 py-2 text-ink-950" onClick={() => { void navigator.clipboard?.writeText(issued.token).then(() => setCopied(true)).catch(() => setCopied(false)); }}>Copy token</button>
      {copied && <p role="status">Copied to clipboard.</p>}
      <p className="text-sm text-ink-300">Run the agent on the target host with this token in its environment. When it enrolls, the host appears in this list within 30 seconds.</p>
      <button className="text-ink-300" onClick={onDone}>Done</button>
    </div>;
  }

  if (!loggedIn) {
    return <form className="mt-4 space-y-4" onSubmit={submitLogin}>
      <p className="text-sm text-ink-300">Enrolling an existing server requires an operator session. Sign in first — the session is kept in memory only.</p>
      <label className="block">Username<input required className="mt-1 block w-full max-w-sm rounded border border-ink-600 bg-ink-900 p-2" value={username} onChange={e => setUsername(e.target.value)} autoComplete="off" /></label>
      <label className="block">Password<input required type="password" className="mt-1 block w-full max-w-sm rounded border border-ink-600 bg-ink-900 p-2" value={password} onChange={e => setPassword(e.target.value)} autoComplete="off" /></label>
      {authError && <p role="alert" className="text-signal-bad">{authError}</p>}
      <button disabled={busy} className="rounded bg-signal-info px-4 py-2 text-ink-950 disabled:opacity-50">Sign in</button>
    </form>;
  }

  return <form className="mt-4 space-y-4" onSubmit={issue}>
    <p className="text-sm text-ink-300">Signed in. Issue a single-use bootstrap token scoped to the new host's hostname.</p>
    <label className="block">Hostname<input required className="mt-1 block w-full max-w-sm rounded border border-ink-600 bg-ink-900 p-2" value={hostname} onChange={e => setHostname(e.target.value)} maxLength={255} /></label>
    {issueError && <p role="alert" className="text-signal-bad">{issueError}</p>}
    <button disabled={busy} className="rounded bg-signal-info px-4 py-2 text-ink-950 disabled:opacity-50">Issue bootstrap token</button>
  </form>;
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
function UnregisterDialog({ host, onClose }: { host: { id: string; name: string }; onClose: () => void }) {
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
      onClose();
    } catch (err) {
      setError(err instanceof ApiFailure ? err.message : "Unregister failed.");
    } finally {
      setBusy(false);
    }
  };
  return <section aria-label={`Unregister ${host.name}`} className="rounded-xl border border-signal-bad p-6">
    <h2 className="text-xl font-semibold">Unregister {host.name}?</h2>
    <ul className="my-3 list-disc pl-5 text-sm text-ink-300">
      <li>The agent's credential is revoked: it receives 401 on its next call and stops reporting.</li>
      <li>The host becomes a tombstone: telemetry and history are retained, never deleted.</li>
      <li>Containers and files on the host are NOT removed; clean them up manually if desired.</li>
    </ul>
    <label className="block text-sm">Type the host id <span className="font-mono">{host.id}</span> to confirm
      <input className="mt-2 block w-full max-w-sm rounded border border-ink-600 bg-ink-900 p-2 font-mono" value={confirmText} onChange={e => setConfirmText(e.target.value)} />
    </label>
    {error && <p role="alert" className="mt-2 text-signal-bad">{error}</p>}
    <div className="mt-4 flex gap-4">
      <button disabled={!enabled || busy} className="rounded bg-signal-bad px-4 py-2 text-ink-950 disabled:opacity-50" onClick={() => void submit()}>Unregister</button>
      <button onClick={onClose}>Cancel</button>
    </div>
  </section>;
}
