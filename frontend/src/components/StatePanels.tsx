/** Full-panel state views: loading, empty, error, API down. */

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

export function ErrorPanel({ title, detail, onRetry }: { title: string; detail?: string; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border border-signal-bad/40 bg-signal-bad/5 p-10 text-center" data-testid="error-panel" role="alert">
      <p className="text-sm font-medium text-signal-bad">{title}</p>
      {detail && <p className="mt-1 text-xs text-ink-300">{detail}</p>}
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 rounded-md border border-ink-600 bg-ink-800 px-3 py-1.5 text-xs text-ink-100 hover:bg-ink-700"
        >
          Retry
        </button>
      )}
    </div>
  );
}
