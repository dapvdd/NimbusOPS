"""Operator bootstrap-token management (PHASE3B_API_CONTRACT.md §3).

ADMIN-only: issue (201, token shown once), list (no token material), revoke
(idempotent; consumed tokens cannot be revoked → 409).
"""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.codes import ErrorCode
from ..core.config import get_settings
from ..core.db import get_db
from ..core.errors import ApiError
from ..models import BootstrapToken
from .operators import require_operator
from ..services.enrollment import issue_bootstrap_token

router = APIRouter(prefix="/api/v1/operators/bootstrap-tokens")


class BootstrapTokenCreateRequest(BaseModel):
    hostname: str = Field(min_length=1, max_length=255)
    expires_in_seconds: int | None = Field(default=None, ge=1, le=3600)
    # Sprint D2: enrollment intent, enforced again at consumption.
    intent: Literal["enroll", "reenroll"] = "enroll"


class BootstrapTokenOut(BaseModel):
    id: str
    hostname: str
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None
    consumed_by_host_id: str | None
    revoked_at: datetime | None


class BootstrapTokenListResponse(BaseModel):
    tokens: list[BootstrapTokenOut]
    count: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("", status_code=201)
def issue_token(
    req: BootstrapTokenCreateRequest,
    op: object = Depends(require_operator(role="ADMIN")),
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    row, plaintext = issue_bootstrap_token(
        db,
        op,
        req.hostname,
        req.expires_in_seconds or settings.bootstrap_token_ttl_seconds,
        intent=req.intent,
    )
    return {
        "id": row.id,
        "hostname": row.hostname,
        "token": plaintext,  # shown once, never logged/stored
        "expires_at": row.expires_at,
        "created_at": row.created_at,
    }


@router.get("")
def list_tokens(
    active: bool | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=200),
    op: object = Depends(require_operator(role="ADMIN")),
    db: Session = Depends(get_db),
) -> BootstrapTokenListResponse:
    """Sprint D2: `?active=true` (unconsumed, unrevoked, unexpired) + `?limit=`
    drive the onboarding hook; the unfiltered shape is unchanged."""
    q = select(BootstrapToken)
    if active:
        now = _now()
        q = q.where(
            BootstrapToken.consumed_at.is_(None),
            BootstrapToken.revoked_at.is_(None),
            BootstrapToken.expires_at > now,
        )
    q = q.order_by(BootstrapToken.created_at.desc())
    if limit is not None:
        q = q.limit(limit)
    rows = db.scalars(q).all()
    return BootstrapTokenListResponse(
        tokens=[
            BootstrapTokenOut(
                id=r.id,
                hostname=r.hostname,
                created_at=r.created_at,
                expires_at=r.expires_at,
                consumed_at=r.consumed_at,
                consumed_by_host_id=r.consumed_by,
                revoked_at=r.revoked_at,
            )
            for r in rows
        ],
        count=len(rows),
    )


@router.delete("/{token_id}")
def revoke_token(
    token_id: str,
    op: object = Depends(require_operator(role="ADMIN")),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(BootstrapToken, token_id)
    if row is None:
        raise ApiError(404, ErrorCode.BOOTSTRAP_TOKEN_INVALID, "unknown bootstrap token")
    if row.consumed_at is not None:
        raise ApiError(409, ErrorCode.BOOTSTRAP_TOKEN_CONSUMED, "token already consumed; cannot revoke")
    if row.revoked_at is None:
        row.revoked_at = _now()
        from ..services.enrollment import record_host_event

        record_host_event(db, None, "BOOTSTRAP_REVOKED", actor=op.username, detail=f"token={row.id} hostname={row.hostname}")
        db.commit()
    return {"id": row.id, "revoked_at": row.revoked_at}
