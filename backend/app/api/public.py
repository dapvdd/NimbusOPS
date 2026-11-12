"""Public (browser) API: /api/v1/health, /api/v1/hosts..."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..version import VERSION
from ..schemas import (
    HealthResponse,
    HostListResponse,
    HostMetricsResponse,
    HostOut,
    MetricsPoint,
    PaginationMeta,
)
from ..services import hosts as host_service
from ..services.hosts import compute_status, require_status_context
from ..models import Telemetry

router = APIRouter(prefix="/api/v1")


def _to_host_out(host, latest: Telemetry | None) -> HostOut:
    stale_s, offline_s = require_status_context(host_service)
    now = datetime.now(timezone.utc)
    status = compute_status(host.last_seen_at, now, stale_s, offline_s)
    return HostOut(
        id=host.id,
        hostname=host.hostname,
        status=status,
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
        is_revoked=host.is_revoked,
        enrollment_status=host.enrollment_status,
        docker_enabled=bool(host.docker_enabled),
    )


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    database = "ok"
    try:
        from sqlalchemy import text

        db.execute(text("SELECT 1"))
    except Exception:
        database = "degraded"
    return HealthResponse(
        status="ok",
        service="nimbusops-control-server",
        version=VERSION,
        server_time=datetime.now(timezone.utc),
        database=database,
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
