import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiFailure } from "../api/client";
import type { BootstrapTokenInfo, Host } from "../api/types";

export function useFleet(intervalMs = 5000) {
  const [hosts, setHosts] = useState<Host[]>([]);
  const [tokens, setTokens] = useState<BootstrapTokenInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiFailure | Error | null>(null);

  const inFlightRef = useRef(false);
  const mountedRef = useRef(true);

  const load = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      const [hostsRes, tokensRes] = await Promise.all([
        api.listHosts(),
        api.listBootstrapTokens({ limit: 50 }).catch(() => ({ tokens: [], count: 0 })),
      ]);
      if (!mountedRef.current) return;
      setHosts(hostsRes?.hosts || []);
      setTokens(tokensRes?.tokens || []);
      setError(null);
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      inFlightRef.current = false;
      if (mountedRef.current) setLoading(false);
    }
  }, []);

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
    tokens,
    loading,
    error,
    refetch: load,
  };
}
