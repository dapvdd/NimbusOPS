"""Agent API: enroll, heartbeat, telemetry — credential-gated."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from ..core.codes import ErrorCode
from ..core.config import get_settings
from ..core.db import get_db
from ..core.errors import ApiError
from ..core.security import verify_enrollment_token
from ..schemas import (
    AgentCommand,
    CommandPollResponse,
    CommandResultRequest,
    CommandResultResponse,
    EnrollRequest,
    EnrollResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    TelemetryRequest,
    TelemetryResponse,
)
from ..services import deployments as deployments_service
from ..services import hosts as host_service

router = APIRouter(prefix="/api/v1/agents")


@router.post("/enroll", response_model=EnrollResponse)
def enroll(req: EnrollRequest, db: Session = Depends(get_db)) -> EnrollResponse:
    settings = get_settings()
    if not settings.enrollment_token:
        host_service.record_enrollment_denied(db, req.hostname, "enrollment disabled (no token configured)")
        raise ApiError(
            503,
            ErrorCode.ENROLLMENT_DISABLED,
            "enrollment is disabled on this server",
        )
    if not verify_enrollment_token(req.enrollment_token):
        host_service.record_enrollment_denied(db, req.hostname, "invalid enrollment token")
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "invalid enrollment token")
    host, token = host_service.enroll_host(db, req)
    return EnrollResponse(host_id=host.id, agent_token=token)


def _agent_token(header_value: str | None) -> str:
    if not header_value or not header_value.startswith("Bearer "):
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "missing agent bearer token")
    return header_value.removeprefix("Bearer ").strip()


@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    req: HeartbeatRequest,
    x_host_id: str = Header(...),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> HeartbeatResponse:
    token = _agent_token(authorization)
    host = host_service.authenticate_host(db, x_host_id, token)
    now = host_service.touch_heartbeat(db, host, req)
    stale_s, offline_s = host_service.require_status_context(host_service)
    return HeartbeatResponse(
        host_id=host.id,
        status=host_service.compute_status(now, now, stale_s, offline_s),
        server_time=now,
        heartbeat_interval_seconds=max(5, stale_s // 3),
    )


@router.post("/telemetry", response_model=TelemetryResponse)
def telemetry(
    req: TelemetryRequest,
    x_host_id: str = Header(...),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> TelemetryResponse:
    token = _agent_token(authorization)
    host = host_service.authenticate_host(db, x_host_id, token)
    row, retained = host_service.record_telemetry(db, host, req)
    stale_s, offline_s = host_service.require_status_context(host_service)
    return TelemetryResponse(
        host_id=host.id,
        recorded_at=row.recorded_at,
        retained=retained,
        status=host_service.compute_status(host.last_seen_at, datetime.now(timezone.utc), stale_s, offline_s),
    )


# ------------------------------------------------------------------ Phase 2


@router.post("/commands/poll", response_model=CommandPollResponse)
def poll_commands(
    x_host_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> CommandPollResponse:
    """Agent claims its QUEUED operations (atomic claim; exactly-once delivery)."""
    if not x_host_id:
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "missing X-Host-Id header")
    token = _agent_token(authorization)
    host_service.authenticate_host(db, x_host_id, token)
    commands: list[AgentCommand] = deployments_service.poll_commands(db, x_host_id)
    return CommandPollResponse(commands=commands)


@router.post("/commands/{operation_id}/result", response_model=CommandResultResponse)
def submit_command_result(
    operation_id: str,
    req: CommandResultRequest,
    x_host_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> CommandResultResponse:
    """Agent reports an operation outcome. First write wins (idempotent)."""
    if not x_host_id:
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "missing X-Host-Id header")
    token = _agent_token(authorization)
    host_service.authenticate_host(db, x_host_id, token)
    op, accepted = deployments_service.submit_result(db, x_host_id, operation_id, req)
    return CommandResultResponse(operation_id=op.id, status=op.status, accepted=accepted)
