/**
 * Backend API client. All fetches go through typed wrappers; network and
 * protocol failures are surfaced as ApiFailure, never swallowed.
 */

import type {
  ApiErrorBody,
  HealthResponse,
  Host,
  HostListResponse,
  HostMetricsResponse,
} from "./types";

export class ApiFailure extends Error {
  /** kind: "http" (server responded with an error status) | "network" */
  kind: "http" | "network";
  status?: number;

  constructor(kind: "http" | "network", message: string, status?: number) {
    super(message);
    this.kind = kind;
    this.status = status;
  }
}

const API_BASE = "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiFailure("network", "Cannot reach the NimbusOps server.");
  }
  if (!resp.ok) {
    let message = `Server returned ${resp.status}`;
    try {
      const body = (await resp.json()) as ApiErrorBody | { detail?: unknown };
      if ("error" in body && body.error?.message) {
        message = body.error.message;
      } else if ("detail" in body) {
        message = `Validation failed (${resp.status})`;
      }
    } catch {
      // Non-JSON error body; keep generic message.
    }
    throw new ApiFailure("http", message, resp.status);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  listHosts: () => request<HostListResponse>("/hosts"),
  getHost: (id: string) => request<Host>(`/hosts/${encodeURIComponent(id)}`),
  getHostMetrics: (id: string, limit = 120) =>
    request<HostMetricsResponse>(`/hosts/${encodeURIComponent(id)}/metrics?limit=${limit}`),
};
