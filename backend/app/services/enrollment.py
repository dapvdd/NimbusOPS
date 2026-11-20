"""Phase 3B secure enrollment: bootstrap-token issue/consume + host creation.

Implements PHASE3B_API_CONTRACT.md §3 (operator bootstrap management) and
§5.1 (secure enroll). Single-use consumption is an atomic UPDATE guarded by
rowcount, so two concurrent agents presenting the same token produce exactly
one host.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.codes import ErrorCode
from ..core.config import get_settings
from ..core.errors import ApiError
from ..core.security import generate_agent_token, hash_session_token
from ..models import BootstrapToken, Host, HostEvent, ProvisioningOwnership

logger = logging.getLogger("nimbusops.enrollment")

MAX_BOOTSTRAP_TTL_SECONDS = 3600


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def record_host_event(
    db: Session, host_id: str | None, event: str, actor: str, detail: str | None = None
) -> None:
    """Append an audit event to the append-only host_events table (O8)."""
    db.add(HostEvent(host_id=host_id, event=event, actor=actor[:64], detail=(detail or "")[:512] or None))


def normalize_hostname(hostname: str) -> str:
    """Sprint D2: hostnames are case-insensitive and whitespace-free.

    Applied at BOTH issue and consumption so `Host-1` and `host-1` are the
    same identity everywhere (fleet listing, token scoping, uniqueness).
    """
    return hostname.strip().lower()


def issue_bootstrap_token(
    db: Session,
    operator,
    hostname: str,
    expires_in_seconds: int = 600,
    *,
    intent: str = "enroll",
) -> tuple[BootstrapToken, str]:
    """Create a single-use bootstrap token. Returns (row, plaintext_once).

    The plaintext token is returned exactly once and never stored.
    Sprint D2: hostname is normalized; `intent` ('enroll'|'reenroll') is
    recorded and enforced again at consumption; at most one ACTIVE token may
    exist per hostname — expired active tokens are revoked first, and a
    concurrent duplicate maps to 409 BOOTSTRAP_TOKEN_ACTIVE.
    """
    hostname = normalize_hostname(hostname)
    if not (1 <= len(hostname) <= 255):
        raise ApiError(422, ErrorCode.INTERNAL, "hostname must be 1-255 characters")
    if intent not in ("enroll", "reenroll"):
        raise ApiError(422, ErrorCode.INTERNAL, "intent must be 'enroll' or 'reenroll'")

    owner = db.scalar(
        select(ProvisioningOwnership)
        .join(Host, ProvisioningOwnership.host_id == Host.id)
        .where(
            Host.hostname == hostname,
            ProvisioningOwnership.disposition.in_(("HELD", "RECONCILING")),
        )
    )
    if owner is not None:
        raise ApiError(
            409, ErrorCode.TARGET_ALREADY_MANAGED,
            "a provisioning job owns this host; release ownership before issuing a bootstrap token",
        )

    settings = get_settings()
    ttl = int(expires_in_seconds or settings.bootstrap_token_ttl_seconds)
    if not (1 <= ttl <= MAX_BOOTSTRAP_TTL_SECONDS):
        raise ApiError(422, ErrorCode.INTERNAL, f"expires_in_seconds must be 1..{MAX_BOOTSTRAP_TTL_SECONDS}")

    now = _utcnow()
    # Revoke expired-but-unconsumed tokens for this hostname so they stop
    # blocking fresh issuance (the active-token guard counts them otherwise).
    for stale in db.scalars(
        select(BootstrapToken).where(
            BootstrapToken.hostname == hostname,
            BootstrapToken.consumed_at.is_(None),
            BootstrapToken.revoked_at.is_(None),
            BootstrapToken.expires_at <= now,
        )
    ).all():
        stale.revoked_at = now

    token = generate_agent_token()  # 256-bit url-safe
    row = BootstrapToken(
        token_hash=hash_session_token(token),
        hostname=hostname,
        created_by=operator.id,
        expires_at=now + timedelta(seconds=ttl),
        intent=intent,
    )
    db.add(row)
    try:
        db.flush()  # trips the partial unique active-token index on duplicates
    except IntegrityError:
        db.rollback()
        raise ApiError(
            409,
            ErrorCode.BOOTSTRAP_TOKEN_ACTIVE,
            "an active bootstrap token already exists for this hostname; revoke it or wait for expiry",
        )
    record_host_event(db, None, "BOOTSTRAP_ISSUED", actor=operator.username, detail=f"hostname={hostname} ttl={ttl}s intent={intent}")
    db.commit()
    logger.info("bootstrap: issued token id=%s hostname=%s ttl=%ss intent=%s", row.id, hostname, ttl, intent)
    return row, token


def consume_bootstrap_token(db: Session, token: str, hostname: str, commit: bool = True) -> BootstrapToken:
    """Validate scope first, then atomically consume a single-use token (T2, T3).

    The consumption itself is one UPDATE ... WHERE consumed_at IS NULL AND
    revoked_at IS NULL AND expires_at > now; rowcount 0 means another agent
    won the race (or the token is dead) and we re-select to map the precise
    typed error. Scope (hostname) is checked before consumption so a wrong-
    hostname attempt never burns the token.

    Sprint D2: the hostname is normalized, and the recorded INTENT is
    re-checked here against the current fleet state — also before the UPDATE:
    - 'enroll' requires the hostname to NOT exist (a revoked host counts as
      existing);
    - 'reenroll' requires it to exist (this is the only un-revoke path);
    - a mismatch maps to BOOTSTRAP_TOKEN_HOSTNAME_MISMATCH with expected vs
      actual (never token material).
    A token issued under one intent therefore cannot silently be used for the
    other after fleet state changes.
    """
    now = _utcnow()
    token_hash = hash_session_token(token)
    row = db.scalar(select(BootstrapToken).where(BootstrapToken.token_hash == token_hash))
    if row is None:
        raise ApiError(401, ErrorCode.BOOTSTRAP_TOKEN_INVALID, "unknown bootstrap token")
    if row.revoked_at is not None:
        raise ApiError(401, ErrorCode.BOOTSTRAP_TOKEN_INVALID, "bootstrap token revoked")
    if _as_utc(row.expires_at) <= now:
        raise ApiError(410, ErrorCode.BOOTSTRAP_TOKEN_EXPIRED, "bootstrap token expired")
    normalized = normalize_hostname(hostname)
    if row.hostname != normalized:
        raise ApiError(
            401,
            ErrorCode.BOOTSTRAP_TOKEN_HOSTNAME_MISMATCH,
            f"bootstrap token is scoped to hostname {row.hostname!r}, not {normalized!r}",
        )
    # Check if already consumed BEFORE intent check, so consuming the same token
    # again on an existing host returns BOOTSTRAP_TOKEN_CONSUMED (409) rather than
    # being rejected early by intent/hostname guards.
    if row.consumed_at is not None:
        raise ApiError(409, ErrorCode.BOOTSTRAP_TOKEN_CONSUMED, "bootstrap token already used")
    # Intent re-check against CURRENT fleet state (pre-UPDATE: rejection never
    # burns the token). Rows issued before this change default to 'enroll'.
    intent = getattr(row, "intent", None) or "enroll"
    existing_host = db.scalar(select(Host).where(Host.hostname == normalized))
    if intent == "enroll" and existing_host is not None:
        raise ApiError(
            409,
            ErrorCode.HOSTNAME_TAKEN,
            "hostname already enrolled; issue a re-enroll token instead",
        )
    if intent == "reenroll" and existing_host is None:
        raise ApiError(404, ErrorCode.HOST_NOT_FOUND, f"host {normalized!r} does not exist; issue an enroll token instead")

    res = db.execute(
        update(BootstrapToken)
        .where(
            BootstrapToken.token_hash == token_hash,
            BootstrapToken.consumed_at.is_(None),
            BootstrapToken.revoked_at.is_(None),
            BootstrapToken.expires_at > now,
        )
        .values(consumed_at=now)
        .execution_options(synchronize_session=False)
    )
    if res.rowcount != 1:
        db.rollback()
        fresh = db.scalar(select(BootstrapToken).where(BootstrapToken.token_hash == token_hash))
        if fresh is None or fresh.revoked_at is not None:
            raise ApiError(401, ErrorCode.BOOTSTRAP_TOKEN_INVALID, "bootstrap token revoked")
        if _as_utc(fresh.expires_at) <= now:
            raise ApiError(410, ErrorCode.BOOTSTRAP_TOKEN_EXPIRED, "bootstrap token expired")
        raise ApiError(409, ErrorCode.BOOTSTRAP_TOKEN_CONSUMED, "bootstrap token already used")
    if commit:
        db.commit()
    return row
