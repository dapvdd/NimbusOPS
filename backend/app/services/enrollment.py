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
from sqlalchemy.orm import Session

from ..core.codes import ErrorCode
from ..core.config import get_settings
from ..core.errors import ApiError
from ..core.security import generate_agent_token, hash_session_token
from ..models import BootstrapToken, HostEvent

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


def issue_bootstrap_token(
    db: Session,
    operator,
    hostname: str,
    expires_in_seconds: int = 600,
) -> tuple[BootstrapToken, str]:
    """Create a single-use bootstrap token. Returns (row, plaintext_once).

    The plaintext token is returned exactly once and never stored.
    """
    hostname = hostname.strip()
    if not (1 <= len(hostname) <= 255):
        raise ApiError(422, ErrorCode.INTERNAL, "hostname must be 1-255 characters")

    settings = get_settings()
    ttl = int(expires_in_seconds or settings.bootstrap_token_ttl_seconds)
    if not (1 <= ttl <= MAX_BOOTSTRAP_TTL_SECONDS):
        raise ApiError(422, ErrorCode.INTERNAL, f"expires_in_seconds must be 1..{MAX_BOOTSTRAP_TTL_SECONDS}")

    token = generate_agent_token()  # 256-bit url-safe
    row = BootstrapToken(
        token_hash=hash_session_token(token),
        hostname=hostname,
        created_by=operator.id,
        expires_at=_utcnow() + timedelta(seconds=ttl),
    )
    db.add(row)
    record_host_event(db, None, "BOOTSTRAP_ISSUED", actor=operator.username, detail=f"hostname={hostname} ttl={ttl}s")
    db.commit()
    logger.info("bootstrap: issued token id=%s hostname=%s ttl=%ss", row.id, hostname, ttl)
    return row, token


def consume_bootstrap_token(db: Session, token: str, hostname: str) -> BootstrapToken:
    """Validate scope first, then atomically consume a single-use token (T2, T3).

    The consumption itself is one UPDATE ... WHERE consumed_at IS NULL AND
    revoked_at IS NULL AND expires_at > now; rowcount 0 means another agent
    won the race (or the token is dead) and we re-select to map the precise
    typed error. Scope (hostname) is checked before consumption so a wrong-
    hostname attempt never burns the token.
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
    if row.hostname != hostname:
        raise ApiError(401, ErrorCode.BOOTSTRAP_TOKEN_INVALID, "bootstrap token not valid for this hostname")

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
    db.commit()
    return row
