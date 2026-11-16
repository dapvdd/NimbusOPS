import type { HostStatus } from "../api/types";

export type ExtendedStatus = HostStatus | "AWAITING" | "EXPIRED";

export interface StatusMeta {
  label: string;
  dot: string;
  text: string;
  bg: string;
  icon: string;
}

export const STATUS_META: Record<ExtendedStatus, StatusMeta> = {
  ONLINE: {
    label: "Online",
    dot: "bg-signal-ok",
    text: "text-signal-ok",
    bg: "bg-signal-ok/10 border-signal-ok/30",
    icon: "●",
  },
  STALE: {
    label: "Stale",
    dot: "bg-signal-warn",
    text: "text-signal-warn",
    bg: "bg-signal-warn/10 border-signal-warn/30",
    icon: "◐",
  },
  OFFLINE: {
    label: "Offline",
    dot: "bg-signal-bad",
    text: "text-signal-bad",
    bg: "bg-signal-bad/10 border-signal-bad/30",
    icon: "○",
  },
  REVOKED: {
    label: "Revoked",
    dot: "bg-purple-400",
    text: "text-purple-300",
    bg: "bg-purple-950/40 border-purple-800/40",
    icon: "⊘",
  },
  AWAITING: {
    label: "Awaiting enrollment",
    dot: "bg-signal-info animate-pulse",
    text: "text-signal-info",
    bg: "bg-signal-info/10 border-signal-info/30",
    icon: "◌",
  },
  EXPIRED: {
    label: "Token expired",
    dot: "bg-signal-warn",
    text: "text-signal-warn",
    bg: "bg-signal-warn/10 border-signal-warn/30",
    icon: "◷",
  },
};

const FALLBACK_META: StatusMeta = {
  label: "Unknown",
  dot: "bg-surface-muted",
  text: "text-ink-400",
  bg: "bg-surface-elevated/40 border-surface-border",
  icon: "?",
};

export function StatusBadge({
  status,
  size = "md",
}: {
  status: ExtendedStatus | (string & {});
  size?: "sm" | "md";
}) {
  const meta = STATUS_META[status as ExtendedStatus] ?? FALLBACK_META;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 ${
        size === "sm" ? "py-0.5 text-[11px]" : "py-1 text-xs"
      } font-medium ${meta.bg} ${meta.text}`}
      data-status={status}
    >
      <span className="font-mono text-xs leading-none" aria-hidden="true">
        {meta.icon}
      </span>
      <span>{meta.label}</span>
    </span>
  );
}
