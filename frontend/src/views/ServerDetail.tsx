import { useParams, useSearchParams } from "react-router-dom";
import HostDetail from "./HostDetail";
import Applications from "./Applications";
import Activity from "./Activity";

/**
 * Host detail container with tab routing. Real hosts only: the browser-local
 * simulated registry is not consulted here — every value on this page comes
 * from the control plane.
 */
export default function ServerDetail() {
  const { hostId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "Overview";

  return (
    <div className="space-y-6">
      <div role="tablist" aria-label="Server views" className="flex flex-wrap gap-2 border-b border-ink-700 pb-3">
        {["Overview", "Monitoring", "Deployments", "Activity"].map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setParams({ tab: t })}
            className={`rounded-lg px-4 py-2 ${tab === t ? "bg-signal-info/15 text-signal-info" : "text-ink-300"}`}
          >
            {t}
          </button>
        ))}
      </div>
      <section role="tabpanel">
        {tab === "Deployments" ? (
          <Applications key={hostId} selectedHostId={hostId} />
        ) : tab === "Activity" ? (
          <Activity hostId={hostId} />
        ) : tab === "Monitoring" ? (
          <HostDetail key={hostId} view="monitoring" />
        ) : (
          <HostDetail key={hostId} />
        )}
      </section>
    </div>
  );
}
