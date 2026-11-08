import type { HostStatus } from "../api/types";

/** Shared visual language for status. Honest colors, no fake healthy. */

export const STATUS_META: Record<HostStatus, { label: string; dot: string; text: string; bg: string }> = {
  ONLINE: {
    label: "Online",
    dot: "bg-signal-ok",
    text: "text-signal-ok",
    bg: "bg-signal-ok/10 border-signal-ok/30",
  },
  STALE: {
    label: "Stale",
    dot: "bg-signal-warn",
    text: "text-signal-warn",
    bg: "bg-signal-warn/10 border-signal-warn/30",
  },
  OFFLINE: {
    label: "Offline",
    dot: "bg-signal-bad",
    text: "text-signal-bad",
    bg: "bg-signal-bad/10 border-signal-bad/30",
  },
};

export function StatusBadge({ status, size = "md" }: { status: HostStatus; size?: "sm" | "md" }) {
  const meta = STATUS_META[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 ${size === "sm" ? "py-0.5 text-[11px]" : "py-1 text-xs"} font-medium ${meta.bg} ${meta.text}`}
      data-status={status}
    >
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
}
