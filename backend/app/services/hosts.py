"""Host/telemetry domain logic: enrollment, auth, status, retention.

This module is deliberately the only place status semantics live, so the
brief's honesty requirements (stale ≠ current, missing ≠ zero) hold
everywhere consistently.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..core.codes import ErrorCode
from ..core.errors import ApiError
from ..core.security import generate_agent_token, hash_token, verify_agent_token
from ..services.enrollment import record_host_event
from ..core.config import get_settings
from ..models import EnrollmentAudit, Host, Telemetry
from ..schemas import EnrollRequest, HeartbeatRequest, TelemetryRequest

logger = logging.getLogger("nimbusops.hosts")

# ---------------------------------------------------------------- helpers


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime | None) -> datetime | None:
    """Normalize DB-provided (possibly naive) datetimes to aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_status(
    last_seen_at: datetime | None,
    now: datetime,
    stale_threshold_seconds: int,
    offline_threshold_seconds: int,
) -> str:
    """Status from last heartbeat only; telemetry staleness is separate."""
    last_seen_at = _as_utc(last_seen_at)
    if last_seen_at is None:
        return "OFFLINE"
    age = (now - last_seen_at).total_seconds()
    if age <= stale_threshold_seconds:
        return "ONLINE"
    if age <= offline_threshold_seconds:
        return "STALE"
    past_offline_window = now - timedelta(seconds=offline_threshold_seconds)
    if last_seen_at >= past_offline_window:
        return "STALE"
    return "OFFLINE"


def telemetry_age_seconds(last_telemetry_at: datetime | None, now: datetime) -> float | None:
    last_telemetry_at = _as_utc(last_telemetry_at)
    if last_telemetry_at is None:
        return None
    return max(0.0, (now - last_telemetry_at).total_seconds())


def require_status_context(db: Session) -> tuple[int, int]:
    from ..core.config import get_settings

    s = get_settings()
    return s.stale_threshold_seconds, s.offline_threshold_seconds


# ------------------------------------------------------------- enrollment


def enroll_host(db: Session, req: EnrollRequest, via_bootstrap: bool = False) -> tuple[Host, str]:
    """Create or re-enroll a host. Returns (host, plaintext_token_once).

    Phase 3B (threat T5): the legacy path never un-revokes — a REVOKED host
    can only be restored through the operator bootstrap flow (via_bootstrap,
    after consume_bootstrap_token validated a single-use operator-issued
    token). Re-enroll of an existing non-revoked host via bootstrap rotates
    the credential; via legacy token it is a plain credential rotation for
    an already-ENROLLED host.
    """
    existing = db.scalar(select(Host).where(Host.hostname == req.hostname))
    if existing is not None:
        if existing.is_revoked and not via_bootstrap:
            raise ApiError(
                409,
                ErrorCode.HOSTNAME_TAKEN,
                "hostname belongs to a revoked host; operator re-enroll required",
            )
        # Re-enrollment: rotate the token, keep host identity (id stable).
        token = generate_agent_token()
        existing.agent_token_hash = hash_token(token)
        existing.is_revoked = False
        existing.revoked_at = None
        existing.enrollment_status = "ENROLLED"
        existing.credential_version = (existing.credential_version or 1) + (1 if via_bootstrap else 0)
        record_host_event(
            db,
            existing.id,
            "RE_ENROLLED" if via_bootstrap else "CREDENTIAL_ROTATED",
            actor="agent",
            detail=f"hostname={req.hostname} via={'bootstrap' if via_bootstrap else 'legacy-token'}",
        )
        db.add(
            EnrollmentAudit(
                hostname=req.hostname,
                outcome="ENROLLED",
                detail="re-enrollment rotated agent token",
            )
        )
        db.commit()
        logger.info(
            "enrollment: re-enrolled host hostname=%s via=%s (token rotated)",
            req.hostname,
            "bootstrap" if via_bootstrap else "legacy",
        )
        return existing, token

    host = Host(
        hostname=req.hostname,
        agent_token_hash=hash_token(token := generate_agent_token()),
        enrollment_status="ENROLLED",
        docker_enabled=False,
        credential_version=1,
        agent_version=req.agent_version,
        platform=req.platform,
        platform_release=req.platform_release,
        cpu_cores=req.cpu_cores,
        total_memory_bytes=req.total_memory_bytes,
        boot_time=req.boot_time,
    )
    db.add(host)
    record_host_event(
        db,
        None,
        "ENROLLED",
        actor="agent",
        detail=f"hostname={req.hostname} via={'bootstrap' if via_bootstrap else 'legacy-token'}",
    )
    db.add(
        EnrollmentAudit(
            hostname=req.hostname,
            outcome="ENROLLED",
            detail=None,
        )
    )
    db.commit()
    logger.info("enrollment: enrolled new host hostname=%s host_id=%s", req.hostname, host.id)
    return host, token


def record_enrollment_denied(db: Session, hostname: str, detail: str) -> None:
    db.add(EnrollmentAudit(hostname=hostname, outcome="DENIED", detail=detail[:255]))
    db.commit()


# ---------------------------------------------------------- agent actions


def _get_host_or_404(db: Session, host_id: str) -> Host:
    host = db.get(Host, host_id)
    if host is None:
        raise ApiError(404, ErrorCode.HOST_NOT_FOUND, f"host {host_id} not found")
    return host


def authenticate_host(db: Session, host_id: str, token: str) -> Host:
    """Resolve host and verify its agent token; raises typed errors.

    Phase 3B (Task 5): dual-hash grace window — the previous credential stays
    valid until `previous_token_expires_at`, then only the current hash works.
    """
    host = _get_host_or_404(db, host_id)
    if host.is_revoked:
        raise ApiError(401, ErrorCode.HOST_REVOKED, "agent credential revoked")
    if verify_agent_token(token, host.agent_token_hash):
        # Current credential. A successful auth on a rotated host whose grace
        # has expired clears the stale previous hash (lazy cleanup).
        if host.previous_token_hash and host.previous_token_expires_at is not None:
            if _as_utc(host.previous_token_expires_at) <= _utcnow():
                host.previous_token_hash = None
                host.previous_token_expires_at = None
                db.commit()
        return host
    # Grace window for the previous credential.
    if (
        host.previous_token_hash
        and host.previous_token_expires_at is not None
        and _as_utc(host.previous_token_expires_at) > _utcnow()
        and verify_agent_token(token, host.previous_token_hash)
    ):
        return host
    raise ApiError(401, ErrorCode.UNAUTHORIZED, "invalid agent credential")


def touch_heartbeat(db: Session, host: Host, req: HeartbeatRequest) -> datetime:
    now = _utcnow()
    host.last_seen_at = now
    for field in ("agent_version", "platform", "platform_release", "cpu_cores", "total_memory_bytes"):
        value = getattr(req, field)
        if value is not None:
            setattr(host, field, value)
    if req.boot_time is not None:
        host.boot_time = req.boot_time
    db.commit()
    return now


def record_telemetry(db: Session, host: Host, req: TelemetryRequest) -> tuple[Telemetry, bool]:
    """Insert telemetry, refresh heartbeat, enforce bounded retention.

    A too-skewed client timestamp is clamped for ordering but the stored
    row keeps the client's recorded_at (documented limitation).
    """
    now = _utcnow()
    row = Telemetry(
        host_id=host.id,
        recorded_at=req.recorded_at,
        cpu_percent=req.cpu_percent,
        memory_used_bytes=req.memory_used_bytes,
        memory_total_bytes=req.memory_total_bytes,
        disk_used_bytes=req.disk_used_bytes,
        disk_total_bytes=req.disk_total_bytes,
        memory_used_percent=(
            req.memory_used_bytes / req.memory_total_bytes * 100.0 if req.memory_total_bytes else 0.0
        ),
        disk_used_percent=(
            req.disk_used_bytes / req.disk_total_bytes * 100.0 if req.disk_total_bytes else 0.0
        ),
    )
    db.add(row)

    stale_s, offline_s = require_status_context(db)
    host.last_seen_at = now
    host.last_telemetry_at = req.recorded_at
    db.commit()

    # Retention: bounded rows per host.
    retained_limit = get_settings().telemetry_retention_rows
    row_count = db.scalar(select(func.count()).select_from(Telemetry).where(Telemetry.host_id == host.id)) or 0
    if row_count > retained_limit:
        excess = row_count - retained_limit
        oldest = db.scalars(
            select(Telemetry.id)
            .where(Telemetry.host_id == host.id)
            .order_by(Telemetry.recorded_at.asc(), Telemetry.id.asc())
            .limit(excess)
        ).all()
        if oldest:
            db.execute(delete(Telemetry).where(Telemetry.id.in_(oldest)))
            db.commit()

    return row, True


def get_host_with_metrics(db: Session, host_id: str) -> tuple[Host, Telemetry | None]:
    host = _get_host_or_404(db, host_id)
    latest = db.scalar(
        select(Telemetry).where(Telemetry.host_id == host_id).order_by(Telemetry.recorded_at.desc(), Telemetry.id.desc())
    )
    return host, latest


def list_hosts_paginated(
    db: Session,
    page: int = 1,
    page_size: int = 50,
    hostname_q: str | None = None,
) -> tuple[list[Host], int]:
    """FR-09: filtered + paginated host listing.

    Returns (page_items, total_matching). Filter is a case-insensitive
    hostname substring match; pagination is 1-based.
    """
    stmt = select(Host).order_by(Host.hostname)
    if hostname_q:
        stmt = stmt.where(Host.hostname.ilike(f"%{hostname_q}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(rows), int(total)


def list_hosts(db: Session) -> list[Host]:
    return list(db.scalars(select(Host).order_by(Host.hostname)).all())


def list_metrics(
    db: Session,
    host_id: str,
    limit: int,
    before: datetime | None,
) -> list[Telemetry]:
    q = select(Telemetry).where(Telemetry.host_id == host_id)
    if before is not None:
        q = q.where(Telemetry.recorded_at < before)
    q = q.order_by(Telemetry.recorded_at.desc(), Telemetry.id.desc()).limit(limit)
    return list(db.scalars(q).all())
