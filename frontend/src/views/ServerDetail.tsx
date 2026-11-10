import { useParams, useSearchParams } from "react-router-dom";
import { listSimServers, isSimulatedHostId } from "../lib/simRegistry";
import HostDetail from "./HostDetail";
import Applications from "./Applications";
import Activity from "./Activity";
import { MetricCard } from "../components/MetricCard";
export default function ServerDetail() {
  const { hostId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "Overview";
  const simulated = isSimulatedHostId(hostId);
  const host = simulated ? listSimServers().find(h => h.id === hostId) : undefined;
  if (simulated && !host) return <h1>Server not found</h1>;
  return <div className="space-y-6">{host && <><p className="text-amber-300">SIMULATED · Browser-only preview · No agent connected</p><h1 className="text-3xl font-semibold">{host.name}</h1><p className="font-mono text-xs text-ink-300">{host.id}</p></>}<div role="tablist" aria-label="Server views" className="flex flex-wrap gap-2 border-b border-ink-700 pb-3">{["Overview", "Monitoring", "Deployments", "Activity"].map(t => <button key={t} role="tab" aria-selected={tab === t} onClick={() => setParams({ tab: t })} className={`rounded-lg px-4 py-2 ${tab === t ? "bg-signal-info/15 text-signal-info" : "text-ink-300"}`}>{t}</button>)}</div><section role="tabpanel">{host ? (tab === "Deployments" ? <p>Simulated hosts have no real deployments.</p> : tab === "Activity" ? <p>SIMULATED server created: {host.created_at}. Local browser history only.</p> : <><p className="mb-4 text-sm text-amber-300">Synthetic sample values — not production telemetry.</p><div className="grid gap-4 sm:grid-cols-3"><MetricCard label="CPU" percent={10 + host.seed % 60} /><MetricCard label="RAM" percent={20 + host.seed % 50} /><MetricCard label="Disk" percent={15 + host.seed % 40} /></div>{tab === "Monitoring" && <p className="mt-4 text-sm text-ink-300">Historical telemetry is not simulated. Only current synthetic samples are shown.</p>}</>)
: tab === "Deployments" ? <Applications key={hostId} selectedHostId={hostId} />
: tab === "Activity" ? <><Activity hostId={hostId} /><p className="mt-3 text-xs text-ink-400">Full audit history: NOT IMPLEMENTED.</p></>
: tab === "Monitoring" ? <HostDetail key={hostId} view="monitoring" />
: <HostDetail key={hostId} />}</section></div>;
}
