"""Agent API: enroll, heartbeat, telemetry — credential-gated."""

import logging
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
from ..services import enrollment as enrollment_service
from ..services import hosts as host_service

router = APIRouter(prefix="/api/v1/agents")
logger = logging.getLogger("nimbusops.agents-api")


@router.post("/enroll", response_model=EnrollResponse)
def enroll(req: EnrollRequest, db: Session = Depends(get_db)) -> EnrollResponse:
    settings = get_settings()
    # Server-side sim isolation: simulated hostnames never enroll.
    if req.hostname.startswith("sim-"):
        host_service.record_enrollment_denied(db, req.hostname, "simulated hostname rejected")
        raise ApiError(400, ErrorCode.SIMULATED_HOST_REJECTED, "simulated hostnames are rejected by the control server")
    # RC2 F01: exactly one enrollment credential is allowed. Accepting both
    # would make the effective trust root ambiguous and untestable.
    if req.bootstrap_token and req.enrollment_token:
        host_service.record_enrollment_denied(db, req.hostname, "conflicting enrollment credentials")
        raise ApiError(
            400,
            ErrorCode.ENROLLMENT_MODE_CONFLICT,
            "provide exactly one of bootstrap_token or enrollment_token",
        )
    if settings.enrollment_mode == "disabled":
        host_service.record_enrollment_denied(db, req.hostname, "enrollment disabled by operator")
        raise ApiError(503, ErrorCode.ENROLLMENT_DISABLED, "enrollment is disabled on this server")
    if req.bootstrap_token:
        # Phase 3B secure path: single-use, operator-issued, hostname-scoped.
        # RC2 F07: token consumption and host creation share one transaction,
        # so a host-creation failure cannot burn the token.
        try:
            token_row = enrollment_service.consume_bootstrap_token(
                db, req.bootstrap_token, req.hostname, commit=False
            )
            host, token = host_service.enroll_host(db, req, via_bootstrap=True)
            # Backfill which host consumed the token (id known only after insert).
            token_row.consumed_by = host.id
            db.commit()
        except Exception:
            db.rollback()
            raise
        return EnrollResponse(host_id=host.id, agent_token=token)
    # Legacy shared-token path (O5 transition). RC2 F08: the secure profile
    # disables it outright; re-enrollment never succeeds through it.
    if settings.enrollment_mode == "bootstrap":
        host_service.record_enrollment_denied(db, req.hostname, "legacy enrollment disabled (bootstrap mode)")
        raise ApiError(
            503,
            ErrorCode.ENROLLMENT_DISABLED,
            "legacy shared-token enrollment is disabled; use an operator-issued bootstrap token",
        )
    if not settings.enrollment_token:
        host_service.record_enrollment_denied(db, req.hostname, "enrollment disabled (no token configured)")
        raise ApiError(
            503,
            ErrorCode.ENROLLMENT_DISABLED,
            "enrollment is disabled on this server",
        )
    if not verify_enrollment_token(req.enrollment_token or ""):
        host_service.record_enrollment_denied(db, req.hostname, "invalid enrollment token")
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "invalid enrollment token")
    host, token = host_service.enroll_host(db, req, via_bootstrap=False)
    return EnrollResponse(host_id=host.id, agent_token=token)


def _agent_token(header_value: str | None) -> str:
    if not header_value or not header_value.startswith("Bearer "):
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "missing agent bearer token")
    return header_value.removeprefix("Bearer ").strip()


def _reject_simulated_host(x_host_id: str | None) -> None:
    """Server-side sim isolation (threat I2): `sim-*` ids never reach services."""
    if x_host_id and x_host_id.startswith("sim-"):
        raise ApiError(
            400,
            ErrorCode.SIMULATED_HOST_REJECTED,
            "simulated host ids are rejected by the control server",
        )


@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    req: HeartbeatRequest,
    x_host_id: str = Header(...),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> HeartbeatResponse:
    _reject_simulated_host(x_host_id)
    token = _agent_token(authorization)
    host = host_service.authenticate_host(db, x_host_id, token)
    now = host_service.touch_heartbeat(db, host, req)
    # Phase 5 (FR-03): optional inventory snapshot (replace-on-report).
    # Tolerated like the agent-side collector: a malformed/failing inventory
    # payload must not fail the heartbeat cycle (heartbeat is already durable).
    if req.inventory is not None:
        try:
            host_service.record_inventory(db, host.id, req.inventory)
        except Exception:  # noqa: BLE001 — inventory never breaks monitoring
            logger.exception("inventory ingest failed for host %s", host.id)
            db.rollback()
    stale_s, offline_s = host_service.require_status_context(host_service)
    return HeartbeatResponse(
        host_id=host.id,
        status=host_service.compute_status(now, now, stale_s, offline_s),
        server_time=now,
        heartbeat_interval_seconds=max(5, stale_s // 3),
        docker_enabled=bool(host.docker_enabled),
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
    _reject_simulated_host(x_host_id)
    if not x_host_id:
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "missing X-Host-Id header")
    token = _agent_token(authorization)
    host = host_service.authenticate_host(db, x_host_id, token)
    commands: list[AgentCommand] = deployments_service.poll_commands(
        db, x_host_id, docker_enabled=bool(host.docker_enabled)
    )
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
    _reject_simulated_host(x_host_id)
    if not x_host_id:
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "missing X-Host-Id header")
    token = _agent_token(authorization)
    host_service.authenticate_host(db, x_host_id, token)
    op, accepted = deployments_service.submit_result(db, x_host_id, operation_id, req)
    return CommandResultResponse(operation_id=op.id, status=op.status, accepted=accepted)
