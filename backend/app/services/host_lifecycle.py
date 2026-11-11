"""Host lifecycle: credential rotation (grace), revoke-to-tombstone, re-enroll.

Implements PHASE3B_API_CONTRACT.md §4. Rotation keeps the previous credential
valid for a grace window (additive columns on hosts, per plan Task 5);
revocation is a tombstone (row retained, agent blocked); re-enroll issues a
fresh bootstrap scoped to the existing hostname — un-revoke happens only when
the agent consumes it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..core.codes import ErrorCode
from ..core.config import get_settings
from ..core.errors import ApiError
from ..core.security import generate_agent_token, hash_token
from ..models import Host
from ..services.enrollment import issue_bootstrap_token, record_host_event

logger = logging.getLogger("nimbusops.lifecycle")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def revoke_host(db: Session, host_id: str, actor: str) -> Host:
    """Revoke-to-tombstone (§4.3): block the agent, keep the row and history.

    Idempotent: revoking a revoked host is a no-op returning the same row.
    Containers are NOT deleted (separate manual operation).
    """
    host = db.get(Host, host_id)
    if host is None:
        raise ApiError(404, ErrorCode.HOST_NOT_FOUND, f"host {host_id} not found")
    if not host.is_revoked:
        now = _utcnow()
        host.is_revoked = True
        host.revoked_at = now
        host.enrollment_status = "REVOKED"
        # Kill any grace window from a prior rotation.
        host.previous_token_hash = None
        host.previous_token_expires_at = None
        record_host_event(db, host.id, "HOST_REVOKED", actor=actor, detail=f"hostname={host.hostname}")
        db.commit()
        logger.info("lifecycle: revoked host %s (%s)", host.hostname, host.id)
    return host


def rotate_credential(db: Session, host_id: str, actor: str, grace_period_seconds: int | None = None) -> tuple[Host, str, datetime]:
    """Rotate the agent credential (§4.2): old token stays valid for grace.

    Returns (host, new_plaintext_once, old_token_expires_at).
    """
    host = db.get(Host, host_id)
    if host is None:
        raise ApiError(404, ErrorCode.HOST_NOT_FOUND, f"host {host_id} not found")
    if host.is_revoked:
        raise ApiError(409, ErrorCode.HOST_REVOKED, "cannot rotate a revoked host; re-enroll instead")

    grace = int(grace_period_seconds if grace_period_seconds is not None else get_settings().credential_rotation_grace_seconds)
    if not (0 <= grace <= 3600):
        raise ApiError(422, ErrorCode.INTERNAL, "grace_period_seconds must be 0..3600")

    new_token = generate_agent_token()
    now = _utcnow()
    host.previous_token_hash = host.agent_token_hash
    host.previous_token_expires_at = now + timedelta(seconds=grace)
    host.agent_token_hash = hash_token(new_token)
    host.credential_version = (host.credential_version or 1) + 1
    record_host_event(
        db,
        host.id,
        "CREDENTIAL_ROTATED",
        actor=actor,
        detail=f"hostname={host.hostname} grace={grace}s version={host.credential_version}",
    )
    db.commit()
    logger.info("lifecycle: rotated credential for %s (grace %ss)", host.hostname, grace)
    return host, new_token, host.previous_token_expires_at


def issue_reenroll_bootstrap(db: Session, host_id: str, actor) -> tuple[Host, str, datetime]:
    """§4.4: fresh bootstrap scoped to the existing hostname.

    Does NOT un-revoke by itself; the host is restored when the agent consumes
    the bootstrap token (enrollment flow). Works for revoked and healthy hosts
    alike (e.g. replacing a lost credential).
    """
    host = db.get(Host, host_id)
    if host is None:
        raise ApiError(404, ErrorCode.HOST_NOT_FOUND, f"host {host_id} not found")
    row, plaintext = issue_bootstrap_token(db, actor, host.hostname)
    record_host_event(db, host.id, "RE_ENROLL_REQUESTED", actor=actor.username, detail=f"bootstrap={row.id}")
    db.commit()
    return host, plaintext, row.expires_at
