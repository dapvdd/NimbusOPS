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
