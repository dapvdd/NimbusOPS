/**
 * Backend API client. All fetches go through typed wrappers; network and
 * protocol failures are surfaced as ApiFailure, never swallowed.
 */

import type {
  ApiErrorBody,
  ContainerStateResponse,
  DeployResponse,
  HealthResponse,
  Host,
  HostListResponse,
  HostMetricsResponse,
  ManagedAppListResponse,
  Operation,
  TemplateListResponse,
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

/** Decode a path segment, returning null when the encoding is malformed. */
function decodeSegment(segment: string): string | null {
  try {
    return decodeURIComponent(segment);
  } catch {
    return null;
  }
}

/**
 * Simulated identities are browser-local and must never reach the backend.
 * Normalise case and percent-encoding so `sim%2D…` or `SIM-…` cannot slip
 * past the check, and refuse malformed identifiers outright.
 */
function assertNotSimulated(path: string, init?: RequestInit): void {
  const segments = path.split(/[/?]/).map(decodeSegment);
  if (segments.some((segment) => segment === null)) {
    throw new ApiFailure("http", "Invalid resource identifier.", 400);
  }
  let hostId: string | undefined;
  if (typeof init?.body === "string") {
    try {
      hostId = (JSON.parse(init.body) as { host_id?: unknown }).host_id as string | undefined;
    } catch {
      // Non-JSON bodies cannot carry a simulated host identity.
      hostId = undefined;
    }
  }
  const decodedHost = typeof hostId === "string" ? decodeSegment(hostId) : undefined;
  if (typeof hostId === "string" && decodedHost === null) {
    throw new ApiFailure("http", "Invalid resource identifier.", 400);
  }
  const simulatedHost = decodedHost?.toLowerCase().startsWith("sim-");
  if (segments.some((segment) => segment!.toLowerCase().startsWith("sim-")) || simulatedHost) {
    throw new ApiFailure("http", "Simulated resources cannot access real infrastructure endpoints.", 400);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  assertNotSimulated(path, init);
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
  // ---------------------------------------------------------------- Phase 2
  listTemplates: () => request<TemplateListResponse>("/templates"),
  listApplications: () => request<ManagedAppListResponse>("/applications"),
  deploy: (hostId: string, templateKey: string) =>
    request<DeployResponse>("/applications/deploy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host_id: hostId, template_key: templateKey }),
    }),
  startApp: (deploymentId: string) =>
    request<DeployResponse>(`/applications/${encodeURIComponent(deploymentId)}/start`, { method: "POST" }),
  stopApp: (deploymentId: string) =>
    request<DeployResponse>(`/applications/${encodeURIComponent(deploymentId)}/stop`, { method: "POST" }),
  getOperation: (operationId: string) =>
    request<Operation>(`/operations/${encodeURIComponent(operationId)}`),
  getContainerState: (deploymentId: string) =>
    request<ContainerStateResponse>(`/applications/${encodeURIComponent(deploymentId)}/container-state`),
};
