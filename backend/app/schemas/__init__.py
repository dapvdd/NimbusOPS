"""Pydantic schemas: agent (request) and public (response) contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------- agent API
class EnrollRequest(BaseModel):
    hostname: str = Field(min_length=1, max_length=255)
    enrollment_token: str = Field(min_length=1, max_length=1024)
    agent_version: str | None = Field(default=None, max_length=64)
    platform: str | None = Field(default=None, max_length=255)
    platform_release: str | None = Field(default=None, max_length=255)
    cpu_cores: int | None = Field(default=None, ge=1, le=4096)
    total_memory_bytes: int | None = Field(default=None, ge=0)
    boot_time: datetime | None = None


class EnrollResponse(BaseModel):
    host_id: str
    agent_token: str  # Returned exactly once; never stored in plaintext.


class HeartbeatRequest(BaseModel):
    agent_version: str | None = Field(default=None, max_length=64)
    platform: str | None = Field(default=None, max_length=255)
    platform_release: str | None = Field(default=None, max_length=255)
    cpu_cores: int | None = Field(default=None, ge=1, le=4096)
    total_memory_bytes: int | None = Field(default=None, ge=0)
    boot_time: datetime | None = None


class HeartbeatResponse(BaseModel):
    host_id: str
    status: Literal["ONLINE", "STALE", "OFFLINE"]
    server_time: datetime
    heartbeat_interval_seconds: int


class TelemetryRequest(BaseModel):
    recorded_at: datetime
    cpu_percent: float = Field(ge=0.0, le=100.0)
    memory_used_bytes: int = Field(ge=0)
    memory_total_bytes: int = Field(gt=0)
    disk_used_bytes: int = Field(ge=0)
    disk_total_bytes: int = Field(gt=0)

    @field_validator("memory_total_bytes")
    @classmethod
    def _memory_total_ge_used(cls, v: int, info) -> int:
        used = info.data.get("memory_used_bytes")
        if used is not None and used > v:
            raise ValueError("memory_used_bytes exceeds memory_total_bytes")
        return v

    @field_validator("disk_total_bytes")
    @classmethod
    def _disk_total_ge_used(cls, v: int, info) -> int:
        used = info.data.get("disk_used_bytes")
        if used is not None and used > v:
            raise ValueError("disk_used_bytes exceeds disk_total_bytes")
        return v


class TelemetryResponse(BaseModel):
    host_id: str
    recorded_at: datetime
    retained: bool
    status: Literal["ONLINE", "STALE", "OFFLINE"]


# -------------------------------------------------------------- public API
class HostStatusInfo(BaseModel):
    state: Literal["ONLINE", "STALE", "OFFLINE"]
    last_seen_at: datetime | None
    last_telemetry_at: datetime | None
    stale_threshold_seconds: int
    offline_threshold_seconds: int


class LatestMetrics(BaseModel):
    recorded_at: datetime
    cpu_percent: float
    memory_used_bytes: int
    memory_total_bytes: int
    memory_used_percent: float
    disk_used_bytes: int
    disk_total_bytes: int
    disk_used_percent: float


MetricsPoint = LatestMetrics  # Same shape on history endpoints.


class HostOut(BaseModel):
    id: str
    hostname: str
    status: Literal["ONLINE", "STALE", "OFFLINE"]
    agent_version: str | None
    platform: str | None
    platform_release: str | None
    cpu_cores: int | None
    total_memory_bytes: int | None
    boot_time: datetime | None
    enrolled_at: datetime
    last_seen_at: datetime | None
    last_telemetry_at: datetime | None
    latest_metrics: LatestMetrics | None  # None => no telemetry yet (not zero)
    is_revoked: bool


class HostListResponse(BaseModel):
    hosts: list[HostOut]
    count: int


class HostMetricsResponse(BaseModel):
    host_id: str
    points: list[MetricsPoint]
    count: int


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["nimbusops-control-server"]
    version: Literal["0.1.0"]
    server_time: datetime
    database: Literal["ok", "degraded"]
