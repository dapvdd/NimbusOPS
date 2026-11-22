/**
 * Applications: approved templates, managed applications, deployment flow.
 *
 * States shown explicitly: Docker unavailable (agent-reported failure code),
 * host offline, deployment pending, operation running, deployment failed,
 * application stopped, application running, unknown result.
 */

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { api, ApiFailure } from "../api/client";
import { useAdmin, useSession } from '../auth/Session';
import type {
  ManagedApp,
  ManagedAppListResponse,
  Operation,
  TemplateListResponse,
} from "../api/types";
import { EmptyPanel, ErrorPanel, LoadingPanel } from "../components/StatePanels";
import { formatUtcTime } from "../lib/format";

const TERMINAL: Operation["status"][] = ["SUCCEEDED", "FAILED", "UNKNOWN"];

function isTerminal(status: Operation["status"]): boolean {
  return TERMINAL.includes(status);
}

type Admission = { id: string | null; pending: boolean; operation: Operation | null; persistenceError: string | null; readFailed: boolean };
const admissions = new Map<string, Admission>();
const admissionListeners = new Set<() => void>();
const emptyAdmission: Admission = { id: null, pending: false, operation: null, persistenceError: null, readFailed: false };
const pendingMarker = "!admission-pending";
function getAdmission(key: string | null): Admission {
  if (!key) return emptyAdmission;
  const cached = admissions.get(key);
  if (cached) return cached;
  let record = { ...emptyAdmission };
  try {
    const saved = window.sessionStorage.getItem(key);
    record = { ...record, id: saved === pendingMarker ? null : saved, pending: saved === pendingMarker };
  } catch {
    record = { ...record, readFailed: true, persistenceError: "Cannot read saved admission references. Writes are blocked; restore tab storage access and reload before attempting recovery." };
  }
  admissions.set(key, record);
  return record;
}
function updateAdmission(key: string, patch: Partial<Admission>, persist = false) {
  let record = { ...getAdmission(key), ...patch };
  if (persist) {
    try {
      if (record.id || record.pending) window.sessionStorage.setItem(key, record.id ?? pendingMarker);
      else window.sessionStorage.removeItem(key);
    } catch {
      record = { ...record, persistenceError: "Operation ID cannot be saved in this tab. Keep this page open and copy the ID before leaving; do not repeat the write." };
    }
  }
  admissions.set(key, record);
  admissionListeners.forEach(notify => notify());
}
function subscribeAdmissions(notify: () => void) {
  admissionListeners.add(notify);
  return () => { admissionListeners.delete(notify); };
}

// Shared tab state outlives components, including a POST still awaiting admission.
function useAdmittedOperation(scope: string, onTerminal: () => void, observeOnly = false) {
  const operatorId = useSession()?.user?.operator_id;
  const admin = useAdmin();
  const storageKey = admin && operatorId ? `nimbusops:admission:v1:${JSON.stringify([operatorId, scope])}` : null;
  const record = useSyncExternalStore(subscribeAdmissions, () => getAdmission(storageKey));
  const { id, operation, persistenceError } = record;
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [checking, setChecking] = useState(false);
  useEffect(() => {
    setError(null);
    setChecking(false);
  }, [storageKey]);
  const admit = (operationId: string) => {
    if (storageKey) updateAdmission(storageKey, { id: operationId, pending: false, operation: null }, true);
  };
  const begin = () => {
    if (!storageKey) return false;
    const current = getAdmission(storageKey);
    if (current.pending || current.readFailed || (current.id && !["SUCCEEDED", "FAILED"].includes(current.operation?.status ?? ""))) return false;
    updateAdmission(storageKey, { pending: true, id: null, operation: null }, true);
    return true;
  };
  const reject = () => {
    if (storageKey) updateAdmission(storageKey, { pending: false }, true);
  };
  useEffect(() => {
    if (!id || !storageKey || observeOnly) return;
    let alive = true;
    let timer: number | undefined;
    const check = async () => {
      setChecking(true);
      try {
        const next = await api.getOperation(id);
        if (!alive) return;
        updateAdmission(storageKey, { operation: next });
        setError(null);
        if (isTerminal(next.status)) {
          onTerminal();
          return;
        }
      } catch (err) {
        if (!alive) return;
        setError(err instanceof ApiFailure ? err.message : "Operation lookup failed");
      } finally {
        if (alive) setChecking(false);
      }
      if (alive) timer = window.setTimeout(check, 2_000);
    };
    void check();
    return () => {
      alive = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [id, storageKey, revision, onTerminal, observeOnly]);
  const unresolved = record.pending || record.readFailed || (id !== null && (!operation || !["SUCCEEDED", "FAILED"].includes(operation.status)));
  return { id, operation, error: storageKey ? error : null, persistenceError, pending: record.pending, checking, unresolved, admit, begin, reject, recheck: () => setRevision(value => value + 1) };
}

function AdmissionNotice({ tracking }: { tracking: ReturnType<typeof useAdmittedOperation> }) {
  if (!tracking.id && !tracking.persistenceError && !tracking.pending) return null;
  return (
    <div className="mt-3 space-y-2 text-xs">
      {tracking.pending && <p>Admission pending or unverified. Do not repeat the write.</p>}
      {tracking.id && <p>Request admitted — operation <span className="font-mono break-all">{tracking.id}</span></p>}
      {(tracking.error || !tracking.operation || tracking.operation.status === "UNKNOWN") && (
        <p className="text-amber-400">Result is unverified. Do not repeat the write; inspect/recheck this operation first.</p>
      )}
      {tracking.error && <p role="alert" className="text-signal-bad">{tracking.error}</p>}
      {tracking.persistenceError && <p role="alert" className="text-signal-bad">{tracking.persistenceError}</p>}
      <button onClick={tracking.recheck} disabled={tracking.checking || !tracking.id} className="rounded-md border border-ink-600 px-3 py-1.5 disabled:opacity-40">
        {tracking.checking ? "Checking operation…" : "Recheck operation (read-only)"}
      </button>
    </div>
  );
}

function AppStateBadge({ app }: { app: ManagedApp }) {
  const op = app.last_operation;
  const state = app.container_state;

  if (!op) {
    return <span className="text-xs text-ink-400">No operations yet</span>;
  }
  if (op.status === "RUNNING" || op.status === "QUEUED") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-signal-info">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-signal-info" />
        {op.status === "QUEUED" ? "Queued" : "Running"} ({op.op_type.toLowerCase()})
      </span>
    );
  }
  if (op.status === "FAILED") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-signal-bad" title={op.error_message ?? ""}>
        <span className="h-1.5 w-1.5 rounded-full bg-signal-bad" />
        Failed: {op.error_code ?? "ERROR"}
      </span>
    );
  }
  if (op.status === "UNKNOWN") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-amber-400">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
        Unknown result
      </span>
    );
  }
  // SUCCEEDED: show real container state.
  if (state === "RUNNING") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-signal-ok">
        <span className="h-1.5 w-1.5 rounded-full bg-signal-ok" />
        Running{app.http_ok === false ? " (HTTP check failing)" : ""}
      </span>
    );
  }
  if (state === "EXITED") {
    return <span className="text-xs text-ink-300">Stopped</span>;
  }
  if (state === "NOT_REPORTED" || state === null) {
    return <span className="text-xs text-ink-400">State not reported yet</span>;
  }
  return <span className="text-xs text-ink-300">{state}</span>;
}

function AppRow({ app, onAction }: { app: ManagedApp; onAction: () => void }) {
  const admin = useAdmin();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tracking = useAdmittedOperation(`lifecycle:${app.deployment_id}`, onAction);
  const deploymentTracking = useAdmittedOperation(`deploy:${app.host_id}:${app.template_key}`, onAction, true);
  const op = app.last_operation;
  const inFlight = (op !== null && !["SUCCEEDED", "FAILED"].includes(op.status)) || deploymentTracking.unresolved;

  const act = async (kind: "start" | "stop") => {
    if (!admin || busy || tracking.unresolved || inFlight || !tracking.begin()) return;
    setBusy(kind);
    setError(null);
    try {
      const response = await (kind === "start" ? api.startApp(app.deployment_id) : api.stopApp(app.deployment_id));
      tracking.admit(response.operation_id);
    } catch (err) {
      tracking.reject();
      setError(err instanceof ApiFailure ? err.message : "Request failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="rounded-lg border border-ink-700 bg-ink-850 p-4" data-testid="app-row">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-sm text-ink-100">{app.container_name}</p>
          <p className="text-xs text-ink-400">
            {app.template_key} on {app.hostname ?? app.host_id}
          </p>
        </div>
        <AppStateBadge app={app} />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
        <a
          href={app.app_url}
          target="_blank"
          rel="noreferrer"
          className="text-signal-info hover:underline"
          onClick={(e) => {
            // Only offer a link when the app is actually reported running.
            if (app.container_state !== "RUNNING" || app.http_ok === false) {
              e.preventDefault();
              setError("Application is not reported running; URL may not respond.");
            }
          }}
        >
          {app.app_url}
        </a>
        {app.reported_at && (
          <span className="text-ink-500">reported {formatUtcTime(app.reported_at)}</span>
        )}
      </div>

      {error && <p className="mt-2 text-xs text-signal-bad" role="alert">{error}</p>}
      <AdmissionNotice tracking={tracking} />
      {deploymentTracking.unresolved && <p className="mt-2 text-xs text-amber-400">Deployment admission is unverified. Lifecycle writes are blocked; inspect the deployment operation first.</p>}
      {tracking.operation && <p className="mt-2 text-xs">Last checked operation: {tracking.operation.status}</p>}

      <div className="mt-3 flex flex-wrap gap-2">
        {admin && (
          <>
            <button
              onClick={() => act("start")}
              disabled={inFlight || tracking.unresolved || busy !== null || app.container_state === "RUNNING"}
              className="rounded-md border border-ink-600 bg-ink-800 px-3 py-1.5 text-xs text-ink-100 hover:bg-ink-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy === "start" ? "Starting…" : "Start"}
            </button>
            <button
              onClick={() => act("stop")}
              disabled={inFlight || tracking.unresolved || busy !== null || app.container_state !== "RUNNING"}
              className="rounded-md border border-ink-600 bg-ink-800 px-3 py-1.5 text-xs text-ink-100 hover:bg-ink-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy === "stop" ? "Stopping…" : "Stop"}
            </button>
          </>
        )}
        <button
          onClick={onAction}
          className="rounded-md border border-ink-600 bg-transparent px-3 py-1.5 text-xs text-ink-300 hover:bg-ink-800"
        >
          Refresh state
        </button>
      </div>
    </div>
  );
}

export default function Applications({ selectedHostId }: { selectedHostId?: string } = {}) {
  const admin = useAdmin();
  const [templates, setTemplates] = useState<TemplateListResponse | null>(null);
  const [apps, setApps] = useState<ManagedAppListResponse | null>(null);
  const [hosts, setHosts] = useState<{ id: string; hostname: string; status: string }[]>([]);
  const [hostId, setHostId] = useState(selectedHostId ?? "");
  const [error, setError] = useState<ApiFailure | null>(null);
  const [loading, setLoading] = useState(true);
  const [deploying, setDeploying] = useState(false);
  const [deployError, setDeployError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [t, a, h] = await Promise.all([api.listTemplates(), api.listApplications(), api.listHosts()]);
      setTemplates(t);
      setApps(a);
      setHosts(h.hosts.map((x) => ({ id: x.id, hostname: x.hostname, status: x.status })));
      if (!hostId && h.hosts.length > 0) {
        const firstOnline = h.hosts.find((x) => x.status === "ONLINE");
        setHostId((firstOnline ?? h.hosts[0]).id);
      }
    } catch (err) {
      setError(err as ApiFailure);
    } finally {
      setLoading(false);
    }
  }, [hostId]);

  const tracking = useAdmittedOperation(`deploy:${hostId}:nginx-demo`, load);
  const activeOp = tracking.operation;

  useEffect(() => {
    load();
    const id = window.setInterval(load, 15_000);
    return () => window.clearInterval(id);
  }, [load]);

  const deployAction = async () => {
    if (!admin || !hostId || deploying || tracking.unresolved || !tracking.begin()) return;
    setDeploying(true);
    setDeployError(null);
    try {
      const resp = await api.deploy(hostId, "nginx-demo");
      tracking.admit(resp.operation_id);
    } catch (err) {
      tracking.reject();
      setDeployError(err instanceof ApiFailure ? err.message : "Deploy request failed");
    } finally {
      setDeploying(false);
    }
  };

  if (loading && !apps && !templates) return <LoadingPanel label="Loading applications" />;
  if (error && !apps && !templates)
    return (
      <ErrorPanel
        title={error.kind === "network" ? "API unavailable" : "Failed to load applications"}
        detail={error.message}
        onRetry={load}
      />
    );

  const selectedHost = hosts.find((h) => h.id === hostId);
  const selectedHostRevoked = selectedHost?.status === "REVOKED";
  const applications = (apps?.applications ?? []).filter(app => !selectedHostId || app.host_id === selectedHostId);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Applications</h1>
        <p className="text-sm text-ink-400">Deploy and manage approved applications on connected hosts.</p>
      </div>

      {/* Deploy panel — ADMIN only; VIEWER never gets a disabled action. */}
      {admin && (
      <section className="rounded-lg border border-ink-700 bg-ink-850 p-4">
        <h2 className="text-sm font-medium text-ink-100">Deploy new application</h2>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="text-xs text-ink-300">
            Host
            <select
              disabled={Boolean(selectedHostId)}
              value={hostId}
              onChange={(e) => setHostId(e.target.value)}
              className="mt-1 block rounded-md border border-ink-600 bg-ink-900 px-2 py-1.5 text-sm text-ink-100"
            >
              {hosts.length === 0 && <option value="">No hosts enrolled</option>}
              {hosts.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.hostname} ({h.status})
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-ink-300">
            Template
            <select
              value="nginx-demo"
              disabled
              className="mt-1 block rounded-md border border-ink-600 bg-ink-900 px-2 py-1.5 text-sm text-ink-100"
            >
              {(templates?.templates ?? []).map((t) => (
                <option key={t.key} value={t.key}>
                  {t.name} ({t.image})
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={deployAction}
            disabled={deploying || tracking.unresolved || !hostId || selectedHostRevoked}
            className="rounded-md bg-signal-info px-4 py-1.5 text-sm font-medium text-ink-950 hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {deploying ? "Requesting…" : "Deploy"}
          </button>
        </div>
        {selectedHostRevoked ? (
          <p className="mt-2 text-xs text-purple-300">
            Credential revoked — re-enroll required from the host page before any deployment can run.
          </p>
        ) : (
          selectedHost && selectedHost.status !== "ONLINE" && (
            <p className="mt-2 text-xs text-amber-400">
              Host is {selectedHost.status}; the operation will run when the agent reconnects.
            </p>
          )
        )}
        {deployError && <p className="mt-2 text-xs text-signal-bad" role="alert">{deployError}</p>}
        <AdmissionNotice tracking={tracking} />

        {activeOp && (
          <div className="mt-3 rounded-md border border-ink-600 bg-ink-900 p-3" data-testid="operation-panel">
            <p className="text-xs text-ink-300">
              Operation <span className="font-mono">{activeOp.id.slice(0, 8)}</span> — {activeOp.op_type}
            </p>
            {activeOp.status === "QUEUED" && (
              <p className="mt-1 text-xs text-ink-400" data-testid="op-progress">Queued — waiting for agent to claim…</p>
            )}
            {activeOp.status === "RUNNING" && (
              <p className="mt-1 text-xs text-signal-info" data-testid="op-progress">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-signal-info mr-1.5" />
                Running on agent…
              </p>
            )}
            {activeOp.status === "SUCCEEDED" && (
              <p className="mt-1 text-xs text-signal-ok" data-testid="op-success">
                Succeeded{activeOp.result?.http_ok === true ? " — application responding" : " — see reported container state below"}
                {typeof activeOp.result?.app_url === "string" && (
                  <>
                    {" "}
                    <a href={activeOp.result.app_url as string} target="_blank" rel="noreferrer" className="text-signal-info hover:underline">
                      {activeOp.result.app_url}
                    </a>
                  </>
                )}
              </p>
            )}
            {activeOp.status === "FAILED" && (
              <p className="mt-1 text-xs text-signal-bad" data-testid="op-failure">
                Failed ({activeOp.error_code}): {activeOp.error_message}
              </p>
            )}
            {activeOp.status === "UNKNOWN" && (
              <p className="mt-1 text-xs text-amber-400" data-testid="op-unknown">
                Result could not be verified — check the host directly.
              </p>
            )}
          </div>
        )}
      </section>
      )}

      {/* Managed applications */}
      <section>
        <h2 className="text-sm font-medium text-ink-100">Managed applications</h2>
        {applications.length === 0 ? (
          <div className="mt-3">
            <EmptyPanel title="No applications deployed" detail="Deploy the Nginx demo to get started." />
          </div>
        ) : (
          <div className="mt-3 space-y-3">
            {applications.map((app) => (
              <AppRow key={app.deployment_id} app={app} onAction={load} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
