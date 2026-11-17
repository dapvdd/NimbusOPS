import React from "react";

export interface InlineAlertProps {
  type?: "info" | "success" | "warn" | "error";
  variant?: "info" | "success" | "warn" | "bad" | "error";
  title?: string;
  message?: string;
  children?: React.ReactNode;
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
  variant,
  title,
  message,
  children,
  action,
  className = "",
}: InlineAlertProps) {
  const effectiveVariant = variant === "bad" ? "error" : (variant || type || "info");
  const style = STYLES[effectiveVariant as keyof typeof STYLES] || STYLES.info;
  const content = children || message;

  return (
    <div
      role={style.role}
      className={`flex items-start justify-between gap-3 rounded-lg border p-3.5 text-sm ${style.bg} ${className}`}
    >
      <div className="space-y-1">
        {title && <p className="font-semibold">{title}</p>}
        {content && <div className="text-ink-100">{content}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
