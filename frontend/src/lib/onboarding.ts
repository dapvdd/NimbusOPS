import type { Host } from "../api/types";

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
