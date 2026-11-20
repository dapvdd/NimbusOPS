import { useEffect, useRef, useState, useCallback } from "react";
import { api, ApiFailure } from "../api/client";
import type { BootstrapTokenInfo, Host } from "../api/types";
import { deriveOnboardingState, enrollmentProof, type OnboardingState } from "../lib/onboarding";

export interface UseOnboardingOptions {
  hostname?: string;
  tokenId?: string;
  enabled?: boolean;
  intervalMs?: number;
}

export function useOnboarding({
  hostname,
  tokenId,
  enabled = true,
  intervalMs = 3000,
}: UseOnboardingOptions = {}) {
  const [token, setToken] = useState<BootstrapTokenInfo | null>(null);
  const [host, setHost] = useState<Host | null>(null);
  const [state, setState] = useState<OnboardingState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiFailure | Error | null>(null);

  const inFlightRef = useRef(false);
  const mountedRef = useRef(true);

  const poll = useCallback(async () => {
    if (inFlightRef.current || !enabled) return;
    inFlightRef.current = true;

    try {
      const [tokenRes, hostRes] = await Promise.all([
        api.listBootstrapTokens({ limit: 50 }),
        api.listHosts(),
      ]);

      if (!mountedRef.current) return;

      let matchedToken: BootstrapTokenInfo | undefined;
      if (tokenId) {
        matchedToken = tokenRes.tokens.find((t) => t.id === tokenId);
      } else if (hostname) {
        const norm = hostname.trim().toLowerCase();
        matchedToken = tokenRes.tokens.find(
          (t) => t.hostname.trim().toLowerCase() === norm && !t.revoked_at
        );
      }

      const matchedHost = enrollmentProof(matchedToken, hostRes.hosts).host;

      setToken(matchedToken || null);
      setHost(matchedHost || null);

      if (matchedToken) {
        setState(deriveOnboardingState(matchedToken));
      } else {
        setState(null);
      }
      setError(null);
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err : new Error(String(err)));
      }
    } finally {
      inFlightRef.current = false;
      if (mountedRef.current) setLoading(false);
    }
  }, [hostname, tokenId, enabled]);

  useEffect(() => {
    mountedRef.current = true;
    if (!enabled) return;

    void poll();

    const interval = setInterval(() => {
      if (document.visibilityState === "visible") {
        void poll();
      }
    }, intervalMs);

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void poll();
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      mountedRef.current = false;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [poll, enabled, intervalMs]);

  const cancel = useCallback(async () => {
    if (!token?.id) return;
    try {
      await api.revokeBootstrapToken(token.id);
      setToken((prev: BootstrapTokenInfo | null) => (prev ? { ...prev, revoked_at: new Date().toISOString() } : null));
      setState("REVOKED");
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    }
  }, [token?.id]);

  return {
    token,
    host,
    state,
    loading,
    error,
    refetch: poll,
    cancel,
  };
}
