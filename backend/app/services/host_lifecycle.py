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

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from ..core.codes import ErrorCode
from ..core.config import get_settings
from ..core.errors import ApiError
from ..core.security import generate_agent_token, hash_token
from ..models import BootstrapToken, Host, ProvisioningGrant, ProvisioningTarget
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

    Every explicit revoke invalidates outstanding authority and emits an audit
    event, including re-revokes. The monotonic revision counter enables the
    admission CAS: a provisioning job that read expected_revocation_revision at
    validation time can detect a concurrent revoke that incremented the counter
    after the validation and before admission, invalidating that grant.
    Containers are NOT deleted (separate manual operation).
    """
    host = db.get(Host, host_id)
    if host is None:
        raise ApiError(404, ErrorCode.HOST_NOT_FOUND, f"host {host_id} not found")
    # Always bump the revision counter — §15.2 MUST for every explicit revoke.
    host.revocation_revision = (host.revocation_revision or 0) + 1
    now = _utcnow()
    if not host.is_revoked:
        host.is_revoked = True
        host.revoked_at = now
    host.enrollment_status = "REVOKED"
    host.previous_token_hash = None
    host.previous_token_expires_at = None
    db.execute(update(BootstrapToken).where(
        BootstrapToken.hostname == host.hostname,
        BootstrapToken.consumed_at.is_(None),
        BootstrapToken.revoked_at.is_(None),
    ).values(revoked_at=now))
    db.execute(update(ProvisioningGrant).where(
        or_(
            ProvisioningGrant.expected_host_id == host.id,
            ProvisioningGrant.result_host_id == host.id,
            ProvisioningGrant.target_id.in_(
                select(ProvisioningTarget.id).where(ProvisioningTarget.host_id == host.id)
            ),
        ),
        ProvisioningGrant.revoked_at.is_(None),
    ).values(revoked_at=int(now.timestamp() * 1000)))
    record_host_event(db, host.id, "HOST_REVOKED", actor=actor,
                      detail=f"hostname={host.hostname} revision={host.revocation_revision}")
    db.commit()
    logger.info("lifecycle: revoked host %s (%s) revision=%d", host.hostname, host.id, host.revocation_revision)
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
    row, plaintext = issue_bootstrap_token(db, actor, host.hostname, intent="reenroll")
    record_host_event(db, host.id, "RE_ENROLL_REQUESTED", actor=actor.username, detail=f"bootstrap={row.id}")
    db.commit()
    return host, plaintext, row.expires_at


def set_environment(db: Session, host: Host, environment: str, actor: str) -> Host:
    """S4-3 (Phase B): operator-set hybrid-cloud classification.

    ADMIN-only at the API layer; validation of the literal is done by the
    request schema (Pydantic → 422). Classification is display/ops grouping —
    never an authorization input. The previous value is kept in the audit
    event so mislabels can be traced.
    """
    old = host.environment
    if old != environment:
        host.environment = environment
        record_host_event(
            db,
            host.id,
            "ENVIRONMENT_SET",
            actor=actor,
            detail=f"hostname={host.hostname} old={old} new={environment}",
        )
        logger.info("lifecycle: environment for %s set %s -> %s", host.hostname, old, environment)
    return host
