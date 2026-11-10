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
  HostListResponse,
  HostMetricsResponse,
  LoginResponse,
  ManagedAppListResponse,
  MeResponse,
  Operation,
  ReenrollResponse,
  RotateCredentialResponse,
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

/**
 * Operator session token lives HERE only (module-scoped, in memory).
 * REACT-AUTH-001 (O1 accepted): never localStorage/sessionStorage/cookies —
 * an XSS reading storage would exfiltrate a long-lived credential; a memory
 * variable dies with the tab.
 */
let operatorSessionToken: string | null = null;

/** Test/visibility hook: the session token is intentionally not persisted. */
export function currentSessionToken(): string | null {
  return operatorSessionToken;
}

function authHeaders(): Record<string, string> {
  return operatorSessionToken ? { Authorization: `Bearer ${operatorSessionToken}` } : {};
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
      headers: { Accept: "application/json", ...authHeaders(), ...init?.headers },
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

  // ---------------------------------------------------------------- Phase 3B
  login: async (username: string, password: string): Promise<LoginResponse> => {
    const body = await request<LoginResponse>("/operators/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    operatorSessionToken = body.session_token; // memory only
    return body;
  },
  logout: async (): Promise<void> => {
    try {
      await request<{ status: string }>("/operators/logout", { method: "POST" });
    } finally {
      operatorSessionToken = null;
    }
  },
  me: () => request<MeResponse>("/operators/me"),
  issueBootstrapToken: (hostname: string, expiresIn?: number) =>
    request<BootstrapTokenIssued>("/operators/bootstrap-tokens", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hostname, ...(expiresIn !== undefined ? { expires_in_seconds: expiresIn } : {}) }),
    }),
  listBootstrapTokens: () => request<BootstrapTokenListResponse>("/operators/bootstrap-tokens"),
  revokeBootstrapToken: (id: string) =>
    request<{ id: string; revoked_at: string | null }>(`/operators/bootstrap-tokens/${encodeURIComponent(id)}`, { method: "DELETE" }),
  patchHost: (id: string, patch: { docker_enabled?: boolean }) =>
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
  issueReenrollBootstrap: (id: string) =>
    request<ReenrollResponse>(`/hosts/${encodeURIComponent(id)}/re-enroll`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_bootstrap_token: true }),
    }),
};
