export interface ToastProps {
  message: string;
  type?: "info" | "success" | "warn" | "error";
  onDismiss?: () => void;
  className?: string;
}

const STYLES = {
  info: "border-signal-info/40 bg-surface-2 text-ink-100",
  success: "border-signal-ok/40 bg-surface-2 text-ink-100",
  warn: "border-signal-warn/40 bg-surface-2 text-ink-100",
  error: "border-signal-bad/40 bg-surface-2 text-ink-100",
};

export function Toast({
  message,
  type = "info",
  onDismiss,
  className = "",
}: ToastProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex items-center justify-between gap-3 rounded-xl border p-4 shadow-xl ${STYLES[type]} ${className}`}
    >
      <div className="flex items-center gap-2 text-sm font-medium">
        <span>{message}</span>
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          aria-label="Dismiss notification"
          className="text-ink-400 hover:text-ink-100 p-1"
        >
          ✕
        </button>
      )}
    </div>
  );
}
