/**
 * Backend API client. All fetches go through typed wrappers; network and
 * protocol failures are surfaced as ApiFailure, never swallowed.
 */

import type {
  ApiErrorBody,
  BootstrapTokenIssued,
  BootstrapTokenListResponse,
  ContainerStateResponse,
  DeployResponse,
  HealthResponse,
  Host,
  HostEventListResponse,
  HostListResponse,
  HostMetricsResponse,
  ManagedAppListResponse,
  MeResponse,
  Operation,
  OperationListResponse,
  ReadinessResponse,
  ReenrollResponse,
  RotateCredentialResponse,
  TemplateListResponse,
} from "./types";

export class ApiFailure extends Error {
  /** kind: "http" (server responded with an error status) | "network" */
  kind: "http" | "network";
  status?: number;
  code?: string;

  constructor(kind: "http" | "network", message: string, status?: number, code?: string) {
    super(message);
    this.kind = kind;
    this.status = status;
    this.code = code;
  }
}

const API_BASE = "/api/v1";

let csrfToken: string | null = null;

export async function refreshCsrf(): Promise<void> {
  const response = await fetch(`${API_BASE}/operators/session/csrf`, { credentials: 'same-origin', cache: 'no-store' });
  if (!response.ok) throw new ApiFailure('http', 'Unable to establish a secure session.', response.status);
  csrfToken = (await response.json()).csrf_token;
}

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
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { Accept: "application/json", ...(csrfToken && init?.method && init.method !== 'GET' ? {'X-CSRF-Token':csrfToken} : {}), ...init?.headers },
    });
  } catch {
    throw new ApiFailure("network", "Cannot reach the NimbusOps server.");
  }
  if (!resp.ok) {
    if (resp.status === 401 && !path.includes('/login')) window.dispatchEvent(new Event('nimbusops:session-expired'));
    let message = `Server returned ${resp.status}`;
    let code: string | undefined;
    try {
      const body = (await resp.json()) as ApiErrorBody | { detail?: unknown };
      if ("error" in body && body.error) {
        if (body.error.message) message = body.error.message;
        if (body.error.code) code = body.error.code;
      } else if ("detail" in body) {
        message = `Validation failed (${resp.status})`;
      }
    } catch {
      // Non-JSON error body; keep generic message.
    }
    throw new ApiFailure("http", message, resp.status, code);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  browserLogin: async (username: string, password: string) => {
    await refreshCsrf();
    const result = await request<{ role: 'ADMIN' | 'VIEWER'; csrf_token: string }>('/operators/session/login', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});
    csrfToken = result.csrf_token;
    return result;
  },
  browserLogout: async () => {
    await refreshCsrf();
    await request('/operators/session/logout', {method:'POST'});
    csrfToken = null;
  },
  health: () => request<HealthResponse>("/health"),
  readiness: async (): Promise<ReadinessResponse> => {
    let resp: Response;
    try {
      resp = await fetch(`${API_BASE}/ready`, {
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
    } catch {
      throw new ApiFailure("network", "Cannot reach the NimbusOps server.");
    }
    if (resp.status === 200 || resp.status === 503) {
      try {
        return (await resp.json()) as ReadinessResponse;
      } catch {
        // Continue to throw error below if body is not valid JSON
      }
    }
    throw new ApiFailure("http", `Readiness check failed (${resp.status})`, resp.status);
  },
  listHosts: () => request<HostListResponse>("/hosts"),
  getHost: (id: string) => request<Host>(`/hosts/${encodeURIComponent(id)}`),
  listHostEvents: (id: string, limit?: number) => {
    const qs = limit !== undefined ? `?limit=${limit}` : "";
    return request<HostEventListResponse>(`/hosts/${encodeURIComponent(id)}/events${qs}`);
  },
  getHostInventory: (id: string) => request<import("./types").HostInventory>(`/hosts/${encodeURIComponent(id)}/inventory`),
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
  // Phase 5 (FR-08): operation history with filters.
  listOperations: (filters: { host_id?: string; status?: string; limit?: number; offset?: number } = {}) => {
    const params = new URLSearchParams();
    if (filters.host_id) params.set("host_id", filters.host_id);
    if (filters.status) params.set("status", filters.status);
    if (filters.limit) params.set("limit", String(filters.limit));
    if (filters.offset) params.set("offset", String(filters.offset));
    const qs = params.toString();
    return request<OperationListResponse>(`/operations${qs ? `?${qs}` : ""}`);
  },
  getContainerState: (deploymentId: string) =>
    request<ContainerStateResponse>(`/applications/${encodeURIComponent(deploymentId)}/container-state`),

  // ---------------------------------------------------------------- Phase 3B
  me: () => request<MeResponse>("/operators/me"),
  issueBootstrapToken: (hostname: string, expiresIn?: number) =>
    request<BootstrapTokenIssued>("/operators/bootstrap-tokens", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hostname, ...(expiresIn !== undefined ? { expires_in_seconds: expiresIn } : {}) }),
    }),
  listBootstrapTokens: (opts?: { active?: boolean; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.active !== undefined) params.set("active", String(opts.active));
    if (opts?.limit !== undefined) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return request<BootstrapTokenListResponse>(`/operators/bootstrap-tokens${qs ? `?${qs}` : ""}`);
  },
  revokeBootstrapToken: (id: string) =>
    request<{ id: string; revoked_at: string | null }>(`/operators/bootstrap-tokens/${encodeURIComponent(id)}`, { method: "DELETE" }),
  patchHost: (id: string, patch: { docker_enabled?: boolean; environment?: "PRIVATE" | "PUBLIC-CLOUD" }) =>
    request<Record<string, unknown>>(`/hosts/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  revokeHost: (id: string) =>
    request<Record<string, unknown>>(`/hosts/${encodeURIComponent(id)}`, { method: "DELETE" }),
  rotateCredential: (id: string, gracePeriodSeconds?: number) =>
    request<RotateCredentialResponse>(`/hosts/${encodeURIComponent(id)}/rotate-credential`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(gracePeriodSeconds !== undefined ? { grace_period_seconds: gracePeriodSeconds } : {}),
    }),
  reenrollHost: (id: string) =>
    request<ReenrollResponse>(`/hosts/${encodeURIComponent(id)}/re-enroll`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_bootstrap_token: true }),
    }),
};
