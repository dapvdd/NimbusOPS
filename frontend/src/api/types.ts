/**
 * Typed contracts mirroring backend/app/schemas. One source of truth for
 * the dashboard: if the backend changes, these change with it.
 */

export type HostStatus = "ONLINE" | "STALE" | "OFFLINE";

export interface LatestMetrics {
  recorded_at: string;
  cpu_percent: number;
  memory_used_bytes: number;
  memory_total_bytes: number;
  memory_used_percent: number;
  disk_used_bytes: number;
  disk_total_bytes: number;
  disk_used_percent: number;
}

export interface Host {
  id: string;
  hostname: string;
  status: HostStatus;
  agent_version: string | null;
  platform: string | null;
  platform_release: string | null;
  cpu_cores: number | null;
  total_memory_bytes: number | null;
  boot_time: string | null;
  enrolled_at: string;
  last_seen_at: string | null;
  last_telemetry_at: string | null;
  latest_metrics: LatestMetrics | null;
  is_revoked: boolean;
}

export interface HostListResponse {
  hosts: Host[];
  count: number;
}

export interface HostDetail extends Host {}

export interface MetricsPoint extends LatestMetrics {}

export interface HostMetricsResponse {
  host_id: string;
  points: MetricsPoint[];
  count: number;
}

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  server_time: string;
  database: "ok" | "degraded";
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
}

// ---------------------------------------------------------------- Phase 2

export type OperationStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "UNKNOWN";
export type OpType = "DEPLOY" | "START" | "STOP";
export type ContainerState =
  | "CREATED"
  | "RUNNING"
  | "PAUSED"
  | "EXITED"
  | "DEAD"
  | "NOT_REPORTED"
  | "UNKNOWN";

export interface Template {
  key: string;
  name: string;
  description: string | null;
  image: string;
  container_port: number;
  host_port: number;
  is_approved: boolean;
}

export interface TemplateListResponse {
  templates: Template[];
}

export interface Operation {
  id: string;
  deployment_id: string;
  host_id: string;
  op_type: OpType;
  status: OperationStatus;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  result: Record<string, unknown> | null;
  error_code: string | null;
  error_message: string | null;
}

export interface DeployResponse {
  operation_id: string;
  deployment_id: string;
  host_id: string;
  template_key: string;
  status: OperationStatus;
  container_name: string;
  app_url: string | null;
  deduplicated: boolean;
}

export interface ManagedApp {
  deployment_id: string;
  host_id: string;
  hostname: string | null;
  template_key: string;
  container_name: string;
  app_url: string;
  last_operation: Operation | null;
  container_state: string | null;
  http_ok: boolean | null;
  reported_at: string | null;
}

export interface ManagedAppListResponse {
  applications: ManagedApp[];
  count: number;
}

export interface ContainerStateResponse {
  deployment_id: string;
  container_state: ContainerState;
  http_ok: boolean | null;
  reported_at: string | null;
  container_name: string;
  app_url: string;
}
