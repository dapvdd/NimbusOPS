/** Full-panel state views: loading, empty, error, API down. */
import { Link } from "react-router-dom";
import { guidanceFor, type GuidanceAction } from "../lib/errorGuidance";
export { InlineAlert } from "../ui/InlineAlert";

export function LoadingPanel({ label = "Loading" }: { label?: string }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-850 p-10 text-center" data-testid="loading-panel">
      <div className="mx-auto h-6 w-6 animate-spin rounded-full border-2 border-ink-600 border-t-signal-info" />
      <p className="mt-3 text-sm text-ink-300">{label}…</p>
    </div>
  );
}

export function EmptyPanel({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-ink-600 bg-ink-900 p-10 text-center" data-testid="empty-panel">
      <p className="text-sm font-medium text-ink-200">{title}</p>
      {detail && <p className="mt-1 text-xs text-ink-400">{detail}</p>}
    </div>
  );
}

export interface ErrorPanelProps {
  error?: unknown;
  title?: string;
  detail?: string;
  code?: string;
  action?: GuidanceAction;
  onRetry?: () => void;
}

export function ErrorPanel({
  error,
  title: propTitle,
  detail: propDetail,
  code: propCode,
  action: propAction,
  onRetry,
}: ErrorPanelProps) {
  const guidance = error ? guidanceFor(error) : undefined;
  const displayTitle = propTitle || guidance?.title || "An error occurred";
  const displayDetail = propDetail || guidance?.detail;
  const displayCode = propCode || guidance?.code;
  const displayAction = propAction || guidance?.action;

  return (
    <div className="rounded-lg border border-signal-bad/40 bg-signal-bad/5 p-10 text-center" data-testid="error-panel" role="alert">
      <p className="text-sm font-medium text-signal-bad">{displayTitle}</p>
      {displayDetail && <p className="mt-1 text-xs text-ink-300">{displayDetail}</p>}
      {displayCode && (
        <p className="mt-2 font-mono text-xs text-ink-400 select-all">
          Code: <code>{displayCode}</code>
        </p>
      )}
      <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
        {onRetry && (
          <button
            onClick={onRetry}
            className="rounded-md border border-ink-600 bg-ink-800 px-3 py-1.5 text-xs text-ink-100 hover:bg-ink-700 focus-visible:outline-2 focus-visible:outline-signal-info"
          >
            Retry
          </button>
        )}
        {displayAction?.to ? (
          <Link
            to={displayAction.to}
            className="rounded-md border border-signal-info bg-signal-info/20 px-3 py-1.5 text-xs font-medium text-signal-info hover:bg-signal-info/30 focus-visible:outline-2 focus-visible:outline-signal-info"
          >
            {displayAction.label}
          </Link>
        ) : displayAction && displayAction.kind !== "refetch" ? (
          <button
            type="button"
            className="rounded-md border border-ink-600 bg-ink-800 px-3 py-1.5 text-xs text-ink-100 hover:bg-ink-700 focus-visible:outline-2 focus-visible:outline-signal-info"
          >
            {displayAction.label}
          </button>
        ) : null}
      </div>
    </div>
  );
}
