import React from "react";

export interface KpiProps {
  label: string;
  value: React.ReactNode;
  unit?: string;
  subtext?: string;
  trend?: "up" | "down" | "neutral";
  className?: string;
}

export function Kpi({
  label,
  value,
  unit,
  subtext,
  className = "",
}: KpiProps) {
  return (
    <div className={`rounded-xl border border-border-subtle bg-surface-2 p-4 ${className}`}>
      <p className="text-xs font-medium text-ink-400">{label}</p>
      <div className="mt-2 flex items-baseline gap-1">
        <span className="text-2xl font-semibold text-ink-100 tabular-nums font-mono">
          {value}
        </span>
        {unit && <span className="text-xs text-ink-400">{unit}</span>}
      </div>
      {subtext && <p className="mt-1 text-xs text-ink-400">{subtext}</p>}
    </div>
  );
}
