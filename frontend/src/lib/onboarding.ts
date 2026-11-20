import type { BootstrapTokenInfo, Host } from "../api/types";

function utcTimestamp(value: string | null | undefined): number {
  if (!value) return NaN;
  // SQLite can return persisted UTC datetimes without an offset.
  return Date.parse(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`);
}

export function enrollmentProof(
  token: BootstrapTokenInfo | undefined,
  hosts: Host[],
  now = Date.now(),
): { host: Host | null; ready: boolean } {
  const host = token?.consumed_at && token.consumed_by_host_id
    ? hosts.find((h) => h.id === token.consumed_by_host_id) ?? null
    : null;
  const consumed = utcTimestamp(token?.consumed_at);
  const fresh = (value: string | null | undefined) => {
    const time = utcTimestamp(value);
    return Number.isFinite(time) && time >= consumed && time <= now && now - time <= 90_000;
  };
  return {
    host,
    ready: !!host && !host.is_revoked && host.enrollment_status !== "REVOKED"
      && host.status === "ONLINE" && fresh(host.last_seen_at)
      && fresh(host.last_telemetry_at) && fresh(host.latest_metrics?.recorded_at),
  };
}

export type OnboardingState = "WAITING" | "EXPIRED" | "CONSUMED" | "REVOKED";

export interface TokenLike {
  expires_at: string;
  consumed_at?: string | null;
  revoked_at?: string | null;
}

export function deriveOnboardingState(
  token: TokenLike,
  now: number = Date.now()
): OnboardingState {
  if (token.consumed_at) return "CONSUMED";
  if (token.revoked_at) return "REVOKED";
  const exp = new Date(token.expires_at).getTime();
  if (exp <= now) return "EXPIRED";
  return "WAITING";
}

export function findHostByHostname(hosts: Host[], hostname: string): Host | undefined {
  const norm = hostname.trim().toLowerCase();
  return hosts.find((h) => h.hostname.trim().toLowerCase() === norm);
}
