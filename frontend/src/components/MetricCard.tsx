/** Metric card with optional bounded bar. Missing data renders as "—". */

import { formatBytes, formatPercent } from "../lib/format";

interface Props {
  label: string;
  percent?: number | null;
  usedBytes?: number | null;
  totalBytes?: number | null;
  hint?: string;
}

export function MetricCard({ label, percent, usedBytes, totalBytes, hint }: Props) {
  const hasData = percent !== null && percent !== undefined && Number.isFinite(percent);
  const barPct = hasData ? Math.min(100, Math.max(0, percent)) : 0;
  const barColor =
    !hasData || percent < 60 ? "bg-signal-info" : percent < 85 ? "bg-signal-warn" : "bg-signal-bad";

  return (
    <div className="rounded-lg border border-ink-700 bg-ink-850 p-4" data-testid="metric-card">
      <div className="flex items-baseline justify-between">
        <span className="text-xs uppercase tracking-wider text-ink-300">{label}</span>
        {hint && <span className="text-[11px] text-ink-400">{hint}</span>}
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="font-mono text-2xl font-semibold text-ink-100" data-testid="metric-value">
          {formatPercent(percent)}
        </span>
        {usedBytes !== undefined && usedBytes !== null && totalBytes ? (
          <span className="text-xs text-ink-300 font-mono">
            {formatBytes(usedBytes)} / {formatBytes(totalBytes)}
          </span>
        ) : null}
      </div>
      <div className="mt-3 h-1.5 rounded bg-ink-700 overflow-hidden">
        {hasData ? (
          <div className={`h-full rounded ${barColor} transition-all`} style={{ width: `${barPct}%` }} />
        ) : (
          <div className="h-full w-full bg-[repeating-linear-gradient(45deg,transparent,transparent_4px,rgba(255,255,255,0.06)_4px,rgba(255,255,255,0.06)_8px)]" />
        )}
      </div>
      {!hasData && <div className="mt-2 text-[11px] text-ink-400">No telemetry received</div>}
    </div>
  );
}
