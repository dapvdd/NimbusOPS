"""Public (browser) API: /api/v1/health, /api/v1/hosts..."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ..core.db import get_db
from .. import version as version_info
from ..schemas import (
    HealthResponse,
    HostEventListResponse,
    HostEventOut,
    HostListResponse,
    HostMetricsResponse,
    HostOut,
    MetricsPoint,
    PaginationMeta,
    ReadinessResponse,
)
from ..services import hosts as host_service
from ..services.hosts import compute_status, effective_status, require_status_context
from ..models import HostEvent, Telemetry

router = APIRouter(prefix="/api/v1")


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_host_out(host, latest: Telemetry | None) -> HostOut:
    stale_s, offline_s = require_status_context(host_service)
    now = datetime.now(timezone.utc)
    # Revocation has two stored spellings (is_revoked flag; tombstoned
    # enrollment_status). Canonicalize so the wire contract is unambiguous:
    # is_revoked is True and enrollment_status is REVOKED for both.
    revoked = bool(host.is_revoked) or host.enrollment_status == "REVOKED"
    connectivity = compute_status(host.last_seen_at, now, stale_s, offline_s)
    status = effective_status(
        is_revoked=revoked,
        enrollment_status=host.enrollment_status,
        last_seen_at=host.last_seen_at,
        now=now,
        stale_s=stale_s,
        offline_s=offline_s,
    )
    grace_until = None
    if host.previous_token_hash is not None and host.previous_token_expires_at is not None:
        expires = _as_utc(host.previous_token_expires_at)
        if expires > now:
            grace_until = expires
    return HostOut(
        id=host.id,
        hostname=host.hostname,
        status=status,
        connectivity=connectivity,
        agent_version=host.agent_version,
        platform=host.platform,
        platform_release=host.platform_release,
        cpu_cores=host.cpu_cores,
        total_memory_bytes=host.total_memory_bytes,
        boot_time=host.boot_time,
        enrolled_at=host.enrolled_at,
        last_seen_at=host.last_seen_at,
        last_telemetry_at=host.last_telemetry_at,
        latest_metrics=(
            MetricsPoint(
                recorded_at=latest.recorded_at,
                cpu_percent=latest.cpu_percent,
                memory_used_bytes=latest.memory_used_bytes,
                memory_total_bytes=latest.memory_total_bytes,
                memory_used_percent=latest.memory_used_percent,
                disk_used_bytes=latest.disk_used_bytes,
                disk_total_bytes=latest.disk_total_bytes,
                disk_used_percent=latest.disk_used_percent,
            )
            if latest is not None
            else None
        ),
        is_revoked=revoked,
        enrollment_status="REVOKED" if revoked else host.enrollment_status,
        docker_enabled=bool(host.docker_enabled),
        environment=host.environment,
        agent_mode=host.agent_mode,
        credential_version=int(host.credential_version or 1),
        credential_grace_until=grace_until,
    )


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    """Liveness + dependency truth.

    RC2 F12: liveness stays HTTP 200 (the process is up), but the body reports
    ``degraded`` when a dependency cannot be reached. Readiness (/ready) is the
    endpoint that must fail for load-balancer routing decisions.
    """
    database = "ok"
    try:
        from sqlalchemy import text

        db.execute(text("SELECT 1"))
    except Exception:
        database = "degraded"
    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        service="nimbusops-control-server",
        version=version_info.VERSION,
        build=version_info.build_id(),
        server_time=datetime.now(timezone.utc),
        database=database,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
def readiness(response: Response, db: Session = Depends(get_db)) -> ReadinessResponse:
    """Readiness probe: 503 while a required dependency is unavailable.

    Exempt from operator read auth (load balancers probe anonymously, like
    /health); the exemption lives in operators.require_read.
    """
    database = "ok"
    try:
        from sqlalchemy import text

        db.execute(text("SELECT 1"))
    except Exception:
        database = "degraded"
    if database != "ok":
        response.status_code = 503
    return ReadinessResponse(
        ready=database == "ok",
        database=database,
        version=version_info.VERSION,
    )


@router.get("/hosts", response_model=HostListResponse)
def list_hosts(
    page: int | None = Query(default=None, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    hostname: str | None = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
) -> HostListResponse:
    if page is None and hostname is None:
        # Legacy shape: full list, no pagination block.
        hosts = host_service.list_hosts(db)
        now = datetime.now(timezone.utc)
        stale_s, offline_s = require_status_context(host_service)
        items = []
        for host in hosts:
            latest = host_service.get_host_with_metrics(db, host.id)[1]
            items.append(_to_host_out(host, latest))
        return HostListResponse(hosts=items, count=len(items))

    # Phase 4 (FR-09): paginated + filtered listing.
    cur = page if page is not None else 1
    rows, total = host_service.list_hosts_paginated(
        db, page=cur, page_size=page_size, hostname_q=hostname)
    now = datetime.now(timezone.utc)
    stale_s, offline_s = require_status_context(host_service)
    items = []
    for host in rows:
        latest = host_service.get_host_with_metrics(db, host.id)[1]
        items.append(_to_host_out(host, latest))
    return HostListResponse(
        hosts=items,
        count=total,
        pagination=PaginationMeta(
            page=cur,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size if total else 0,
        ),
    )


@router.get("/hosts/{host_id}", response_model=HostOut)
def get_host(host_id: str, db: Session = Depends(get_db)) -> HostOut:
    host, latest = host_service.get_host_with_metrics(db, host_id)
    return _to_host_out(host, latest)


@router.get("/hosts/{host_id}/events", response_model=HostEventListResponse)
def list_host_events(
    host_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> HostEventListResponse:
    from sqlalchemy import select

    host = host_service._get_host_or_404(db, host_id)
    rows = db.scalars(
        select(HostEvent)
        .where(HostEvent.host_id == host.id)
        .order_by(HostEvent.at.desc())
        .limit(limit)
    ).all()
    events = [
        HostEventOut(
            id=r.id,
            host_id=r.host_id,
            event=r.event,
            actor=r.actor,
            detail=r.detail,
            at=r.at,
            created_at=r.at,
        )
        for r in rows
    ]
    return HostEventListResponse(events=events, count=len(events))


@router.get("/hosts/{host_id}/metrics", response_model=HostMetricsResponse)
def get_host_metrics(
    host_id: str,
    limit: int = Query(default=120, ge=1, le=1440),
    before: datetime | None = None,
    db: Session = Depends(get_db),
) -> HostMetricsResponse:
    host = host_service._get_host_or_404(db, host_id)
    rows = host_service.list_metrics(db, host_id, limit=limit, before=before)
    return HostMetricsResponse(
        host_id=host.id,
        points=[
            MetricsPoint(
                recorded_at=r.recorded_at,
                cpu_percent=r.cpu_percent,
                memory_used_bytes=r.memory_used_bytes,
                memory_total_bytes=r.memory_total_bytes,
                memory_used_percent=r.memory_used_percent,
                disk_used_bytes=r.disk_used_bytes,
                disk_total_bytes=r.disk_total_bytes,
                disk_used_percent=r.disk_used_percent,
            )
            for r in rows
        ],
        count=len(rows),
    )


@router.get("/hosts/{host_id}/inventory")
def get_host_inventory(host_id: str, db: Session = Depends(get_db)) -> object:
    """Phase 5 (FR-03): latest docker inventory snapshot for a host.

    404 (structured INVENTORY_NOT_FOUND) when the host has never reported
    inventory — stale data is never fabricated or labeled fresh.
    """
    from ..core.codes import ErrorCode
    from ..core.errors import ApiError

    snapshot = host_service.get_inventory(db, host_id)
    if snapshot is None:
        # Distinguish unknown host from host-without-inventory.
        host_service._get_host_or_404(db, host_id)
        raise ApiError(404, ErrorCode.INVENTORY_NOT_FOUND, "no inventory snapshot reported by this host")
    return snapshot
