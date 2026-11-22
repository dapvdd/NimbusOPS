import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiFailure } from "../api/client";
import type { BootstrapTokenInfo, Host } from "../api/types";
import { useAdmin } from "../auth/Session";

export function useFleet(intervalMs = 5000) {
  const admin = useAdmin();
  const [hosts, setHosts] = useState<Host[]>([]);
  const [tokens, setTokens] = useState<BootstrapTokenInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiFailure | Error | null>(null);
  const [tokensError, setTokensError] = useState<Error | null>(null);

  const inFlightRef = useRef(false);
  const mountedRef = useRef(true);

  const load = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      const [hostsRes, tokensRes] = await Promise.allSettled([
        api.listHosts(),
        admin ? api.listBootstrapTokens({ limit: 50 }) : Promise.resolve({ tokens: [], count: 0 }),
      ]);
      if (!mountedRef.current) return;
      if (hostsRes.status === "fulfilled") {
        setHosts(hostsRes.value?.hosts || []);
        setError(null);
      } else {
        setError(hostsRes.reason instanceof Error ? hostsRes.reason : new Error(String(hostsRes.reason)));
      }
      if (tokensRes.status === "fulfilled") {
        setTokens(tokensRes.value?.tokens || []);
        setTokensError(null);
      } else {
        setTokens([]);
        setTokensError(tokensRes.reason instanceof Error ? tokensRes.reason : new Error(String(tokensRes.reason)));
      }
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      inFlightRef.current = false;
      if (mountedRef.current) setLoading(false);
    }
  }, [admin]);

  useEffect(() => {
    mountedRef.current = true;
    void load();

    const interval = setInterval(() => {
      if (document.visibilityState === "visible") {
        void load();
      }
    }, intervalMs);

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void load();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      mountedRef.current = false;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [load, intervalMs]);

  return {
    hosts,
    tokens: admin ? tokens : [],
    loading,
    error,
    tokensError: admin ? tokensError : null,
    tokensAccess: admin ? "allowed" as const : "denied" as const,
    refetch: load,
  };
}
