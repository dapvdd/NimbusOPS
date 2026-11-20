"""Pydantic schemas: agent (request) and public (response) contracts."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------- agent API
class EnrollRequest(BaseModel):
    hostname: str = Field(min_length=1, max_length=255)
    # Legacy shared enrollment token (O5: accepted through the Phase 3B
    # transition; removed in Phase 4).
    enrollment_token: str | None = Field(default=None, min_length=1, max_length=1024)
    # Phase 3B: single-use operator-issued bootstrap token (preferred path).
    bootstrap_token: str | None = Field(default=None, min_length=1, max_length=1024)
    agent_version: str | None = Field(default=None, max_length=64)
    platform: str | None = Field(default=None, max_length=255)
    platform_release: str | None = Field(default=None, max_length=255)
    cpu_cores: int | None = Field(default=None, ge=1, le=4096)
    total_memory_bytes: int | None = Field(default=None, ge=0)
    boot_time: datetime | None = None
    # Phase 4 (FR-19): optional environment metadata at enroll time.
    environment: Literal["PRIVATE", "PUBLIC-CLOUD"] | None = None


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
    # Sprint D3: mode the running agent reports. Absence (None) is meaningful —
    # it clears any previously reported mode ("not reported" now).
    agent_mode: Literal["executor", "telemetry-only"] | None = None
    # Phase 5 (FR-03): optional docker inventory snapshot (replace-on-report).
    inventory: "InventoryPayload | None" = None


class InventoryContainer(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    names: str = Field(min_length=1, max_length=255)
    image: str = Field(min_length=1, max_length=255)
    state: str = Field(min_length=1, max_length=32)
    managed: bool = False
    deployment_id: str | None = Field(default=None, max_length=64)


class InventoryPayload(BaseModel):
    containers: list[InventoryContainer] = Field(max_length=500)
    observed_at: datetime


class HeartbeatResponse(BaseModel):
    host_id: str
    status: Literal["ONLINE", "STALE", "OFFLINE"]
    server_time: datetime
    heartbeat_interval_seconds: int
    # Phase 3B (§7.2): agent refuses Docker ops when False.
    docker_enabled: bool = False


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

    @field_validator("recorded_at")
    @classmethod
    def normalize_recorded_at(cls, value: datetime) -> datetime:
        """Restore the UTC timezone SQLite drops on persisted telemetry."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


MetricsPoint = LatestMetrics  # Same shape on history endpoints.


class HostOut(BaseModel):
    id: str
    hostname: str
    # Sprint D1: effective display status — REVOKED beats connectivity.
    status: Literal["ONLINE", "STALE", "OFFLINE", "REVOKED"]
    # Sprint D1: pure heartbeat connectivity, kept for clients that must not
    # see revocation folded into their connectivity logic.
    connectivity: Literal["ONLINE", "STALE", "OFFLINE"]
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
    # Phase 3B (§7.1): lifecycle state; REVOKED is canonical over is_revoked.
    enrollment_status: Literal["PENDING", "ENROLLED", "ONLINE", "STALE", "OFFLINE", "REVOKED"]
    docker_enabled: bool
    # Phase 4 (FR-19): environment grouping metadata.
    environment: Literal["PRIVATE", "PUBLIC-CLOUD"]
    # Sprint D3: mode the running agent reported (null = not reported).
    agent_mode: Literal["executor", "telemetry-only"] | None
    # Sprint D1: rotation bookkeeping for the UI countdown.
    credential_version: int
    # Null unless a rotation grace window is ACTIVE (hash set AND expires_at > now).
    credential_grace_until: datetime | None

    @field_validator(
        "boot_time",
        "enrolled_at",
        "last_seen_at",
        "last_telemetry_at",
        "credential_grace_until",
    )
    @classmethod
    def normalize_host_timestamp(cls, value: datetime | None) -> datetime | None:
        """Expose persisted UTC instants unambiguously to browser clients."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class HostEventOut(BaseModel):
    id: int
    host_id: str | None
    event: str
    actor: str
    detail: str | None
    at: datetime
    created_at: datetime


class HostEventListResponse(BaseModel):
    events: list[HostEventOut]
    count: int


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class HostListResponse(BaseModel):
    hosts: list[HostOut]
    count: int
    # Phase 4 (FR-09): present only when ?page/ is used (additive, optional).
    pagination: PaginationMeta | None = None


class HostMetricsResponse(BaseModel):
    host_id: str
    points: list[MetricsPoint]
    count: int


class HealthResponse(BaseModel):
    # RC2 F12: a dependency failure must be visible in the payload, not hidden
    # behind a static "ok".
    status: Literal["ok", "degraded"]
    service: Literal["nimbusops-control-server"]
    version: str
    # RC2 F15: immutable build marker (NIMBUSOPS_BUILD_SHA), "unknown" if absent.
    build: str
    server_time: datetime
    database: Literal["ok", "degraded"]


class ReadinessResponse(BaseModel):
    ready: bool
    database: Literal["ok", "degraded"]
    version: str


# ------------------------------------------------------------------ Phase 2


class TemplateOut(BaseModel):
    key: str
    name: str
    description: str | None
    image: str
    container_port: int
    host_port: int
    is_approved: bool


class TemplateListResponse(BaseModel):
    templates: list[TemplateOut]


class DeployRequest(BaseModel):
    host_id: str = Field(min_length=1, max_length=64)
    template_key: str = Field(min_length=1, max_length=64)


class OperationOut(BaseModel):
    id: str
    deployment_id: str
    host_id: str
    op_type: Literal["DEPLOY", "START", "STOP", "RESTART"]
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "UNKNOWN"]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    result: dict | None = None
    error_code: str | None = None
    error_message: str | None = None


class OperationListResponse(BaseModel):
    operations: list[OperationOut]
    count: int
    # RC2 F10: total matching rows and the window offset, so clients can page
    # toward older history instead of silently losing recent operations.
    total: int
    offset: int = 0


class OperationEventOut(BaseModel):
    id: int
    at: datetime
    event: str
    detail: str | None = None


class OperationEventsResponse(BaseModel):
    operation_id: str
    events: list[OperationEventOut]


class DeployResponse(BaseModel):
    operation_id: str
    deployment_id: str
    host_id: str
    template_key: str
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "UNKNOWN"]
    container_name: str
    app_url: str | None = None
    deduplicated: bool = False
    # Phase 5: op type echoed (RESTART/START/STOP/DEPLOY) for UI clarity.
    op_type: Literal["DEPLOY", "START", "STOP", "RESTART"] = "DEPLOY"


class ManagedAppOut(BaseModel):
    deployment_id: str
    host_id: str
    hostname: str | None = None
    template_key: str
    container_name: str
    app_url: str
    # Latest operation state for this deployment (honest unknown when none).
    last_operation: OperationOut | None
    # Agent-reported container state, if any.
    container_state: str | None
    http_ok: bool | None
    reported_at: datetime | None


class ManagedAppListResponse(BaseModel):
    applications: list[ManagedAppOut]
    count: int


class ContainerStateResponse(BaseModel):
    deployment_id: str
    container_state: Literal["CREATED", "RUNNING", "PAUSED", "EXITED", "DEAD", "NOT_REPORTED", "UNKNOWN"]
    http_ok: bool | None
    reported_at: datetime | None
    container_name: str
    app_url: str


class CommandPollResponse(BaseModel):
    commands: list["AgentCommand"]


class AgentCommand(OperationOut):
    """Command delivered to an agent: operation plus execution payload."""
    template: dict | None = None  # image/ports/name for DEPLOY ops
    # RC2 F07: fencing generation for this claim; echoed back with the result.
    claim_generation: int = 0


class CommandResultRequest(BaseModel):
    status: Literal["SUCCEEDED", "FAILED", "UNKNOWN"]
    result: dict | None = None
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, max_length=512)
    # Optional for backward compatibility; enforced when present.
    claim_generation: int | None = Field(default=None, ge=0)


class CommandResultResponse(BaseModel):
    operation_id: str
    # A rejected (accepted=False) result can leave the operation non-terminal
    # (stale fencing) or already terminal (duplicate delivery), so the honest
    # current state is echoed rather than only terminal states.
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "UNKNOWN"]
    accepted: bool


# ------------------------------------------------------------------ Phase 3B


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    session_token: str
    operator_id: str
    role: Literal["ADMIN", "VIEWER"]

    expires_at: datetime


class MeResponse(BaseModel):
    operator_id: str
    username: str
    role: Literal["ADMIN", "VIEWER"]
