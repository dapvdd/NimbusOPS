import React from "react";

export interface PanelProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = "",
  ...props
}: PanelProps) {
  return (
    <section
      className={`rounded-xl border border-border-subtle bg-surface-1 p-6 ${className}`}
      {...props}
    >
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-4 border-b border-border-subtle pb-4">
          <div>
            {title && <h2 className="text-lg font-semibold text-ink-100">{title}</h2>}
            {subtitle && <p className="mt-1 text-xs text-ink-400">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
