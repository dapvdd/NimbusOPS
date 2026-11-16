import React from "react";

export interface InlineAlertProps {
  type?: "info" | "success" | "warn" | "error";
  title?: string;
  message: string;
  action?: React.ReactNode;
  className?: string;
}

const STYLES = {
  info: {
    bg: "bg-signal-info/10 border-signal-info/30 text-signal-info",
    role: "status",
  },
  success: {
    bg: "bg-signal-ok/10 border-signal-ok/30 text-signal-ok",
    role: "status",
  },
  warn: {
    bg: "bg-signal-warn/10 border-signal-warn/30 text-signal-warn",
    role: "alert",
  },
  error: {
    bg: "bg-signal-bad/10 border-signal-bad/30 text-signal-bad",
    role: "alert",
  },
};

export function InlineAlert({
  type = "info",
  title,
  message,
  action,
  className = "",
}: InlineAlertProps) {
  const style = STYLES[type];

  return (
    <div
      role={style.role}
      className={`flex items-start justify-between gap-3 rounded-lg border p-3.5 text-sm ${style.bg} ${className}`}
    >
      <div className="space-y-1">
        {title && <p className="font-semibold">{title}</p>}
        <p className="text-ink-100">{message}</p>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
