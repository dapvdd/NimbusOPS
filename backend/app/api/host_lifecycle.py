"""Operator host-lifecycle endpoints (PHASE3B_API_CONTRACT.md §4).

All ADMIN-only: PATCH docker_enabled, rotate-credential, DELETE (revoke),
re-enroll bootstrap issuance.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.codes import ErrorCode
from ..core.db import get_db
from ..core.errors import ApiError
from ..models import Host
from ..services import host_lifecycle
from .operators import require_operator

router = APIRouter(prefix="/api/v1/hosts")


class HostPatchRequest(BaseModel):
    docker_enabled: bool | None = Field(default=None)


class RotateCredentialRequest(BaseModel):
    grace_period_seconds: int | None = Field(default=None, ge=0, le=3600)


class ReenrollRequest(BaseModel):
    new_bootstrap_token: bool = True


class LifecycleHostOut(BaseModel):
    id: str
    hostname: str
    enrollment_status: str
    docker_enabled: bool
    is_revoked: bool
    revoked_at: datetime | None
    credential_version: int


def _host_out(host: Host) -> dict:
    return {
        "id": host.id,
        "hostname": host.hostname,
        "enrollment_status": host.enrollment_status,
        "docker_enabled": bool(host.docker_enabled),
        "is_revoked": bool(host.is_revoked),
        "revoked_at": host.revoked_at,
        "credential_version": host.credential_version or 1,
    }


def _get_host_or_404(db: Session, host_id: str) -> Host:
    host = db.get(Host, host_id)
    if host is None:
        raise ApiError(404, ErrorCode.HOST_NOT_FOUND, f"host {host_id} not found")
    return host


@router.patch("/{host_id}")
def patch_host(
    host_id: str,
    req: HostPatchRequest,
    op: object = Depends(require_operator(role="ADMIN")),
    db: Session = Depends(get_db),
) -> dict:
    """§4.1: only `docker_enabled` is operator-settable here."""
    if req.docker_enabled is None:
        raise ApiError(422, ErrorCode.INTERNAL, "no settable fields in request")
    host = _get_host_or_404(db, host_id)
    host.docker_enabled = req.docker_enabled
    from ..services.enrollment import record_host_event

    record_host_event(db, host.id, "DOCKER_ENABLED" if req.docker_enabled else "DOCKER_DISABLED", actor=op.username)
    db.commit()
    return _host_out(host)


@router.post("/{host_id}/rotate-credential")
def rotate_credential(
    host_id: str,
    req: RotateCredentialRequest,
    op: object = Depends(require_operator(role="ADMIN")),
    db: Session = Depends(get_db),
) -> dict:
    host, new_token, old_expires = host_lifecycle.rotate_credential(db, host_id, op.username, req.grace_period_seconds)
    return {
        "host_id": host.id,
        "new_agent_token": new_token,  # shown once
        "old_token_expires_at": old_expires,
    }


@router.delete("/{host_id}")
def revoke_host(
    host_id: str,
    op: object = Depends(require_operator(role="ADMIN")),
    db: Session = Depends(get_db),
) -> dict:
    host = host_lifecycle.revoke_host(db, host_id, op.username)
    return _host_out(host)


@router.post("/{host_id}/re-enroll", status_code=201)
def reenroll_host(
    host_id: str,
    req: ReenrollRequest,
    op: object = Depends(require_operator(role="ADMIN")),
    db: Session = Depends(get_db),
) -> dict:
    host, plaintext, expires = host_lifecycle.issue_reenroll_bootstrap(db, host_id, op)
    return {
        "bootstrap_token": plaintext,  # shown once
        "expires_at": expires,
        "hostname": host.hostname,
    }
