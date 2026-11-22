"""ADMIN-only target discovery. Server policy is the authorization boundary."""

import json
import os
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import Operator
from ..models.provisioning import ProvisioningEvent, ProvisioningJob
from ..provisioning.ssh import Target, load_targets, preflight
from ..services.provisioning import (
    confirm_plan,
    confirmation_hash,
    recover_confirmation,
    retry_plan,
    save_plan,
)
from .operators import require_operator

router = APIRouter(prefix="/api/v1/provisioning")
admin = require_operator(role="ADMIN")


class PreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_id: str = Field(min_length=1, max_length=255)


def configured_targets() -> dict[str, Target]:
    path = os.environ.get("NIMBUSOPS_SSH_TARGETS_FILE")
    try:
        return load_targets(Path(path)) if path else {}
    except (ValueError, OSError):
        raise HTTPException(503, "TARGET_POLICY_INVALID") from None


@router.get("/targets")
def targets(op: Annotated[Operator, Depends(admin)]) -> dict[str, Any]:
    return {
        "targets": [
            {"id": t.id, "hostname": t.hostname, "address": t.address}
            for t in configured_targets().values()
        ]
    }


@router.post("/preflight")
def inspect_target(
    req: PreflightRequest,
    op: Annotated[Operator, Depends(admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    target = configured_targets().get(req.target_id)
    if target is None:
        raise HTTPException(404, "TARGET_NOT_AUTHORIZED")
    try:
        facts = preflight(target)
    except ValueError:
        raise HTTPException(409, "PREFLIGHT_REJECTED") from None
    try:
        plan = save_plan(db, op.id, target, facts)
    except ValueError:
        raise HTTPException(409, "EXISTING_IDENTITY_OR_BINDING") from None
    return {
        "target_id": target.id,
        "facts": facts,
        "validation_id": plan.id,
        "approval_hash": plan.plan_hash,
        "expires_at": plan.expires_at,
        "changes": [
            "Install pinned telemetry-only agent",
            "Create dedicated service user",
            "Create and enable systemd service",
            "No Docker permissions",
        ],
        "installation_enabled": True,
    }


class ConfirmRequest(PreflightRequest):
    validation_id: str = Field(min_length=1, max_length=36)
    approval_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed: Literal[True]
    idempotency_key: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$"
    )


@router.post("/confirm", status_code=202)
def confirm(
    req: ConfirmRequest,
    op: Annotated[Operator, Depends(admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    try:
        job = recover_confirmation(
            db,
            op.id,
            req.idempotency_key,
            confirmation_hash(req.target_id, req.validation_id, req.approval_hash),
        )
        if job is None:
            target = configured_targets().get(req.target_id)
            if target is None:
                raise HTTPException(404, "TARGET_NOT_AUTHORIZED")
            job = confirm_plan(
                db,
                op.id,
                target,
                req.validation_id,
                req.approval_hash,
                idempotency_key=req.idempotency_key,
            )
    except ValueError:
        db.rollback()
        raise HTTPException(409, "APPROVAL_INVALID_OR_TARGET_RESERVED") from None
    return {"id": job.id, "state": job.state}


@router.get("/requests/{idempotency_key}")
def recover(
    idempotency_key: str,
    op: Annotated[Operator, Depends(admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    job = recover_confirmation(db, op.id, idempotency_key)
    if job is None:
        raise HTTPException(404, "JOB_NOT_FOUND")
    return {"id": job.id, "state": job.state}


def job_metadata(job: ProvisioningJob) -> dict[str, Any]:
    """Project the public history allowlist, never stored plans or credentials."""
    return {
        "id": job.id,
        "target_id": job.target_id,
        "method": "Automatic Setup",
        "operation": job.operation,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "state": job.state,
        "step": job.step,
        "reason_code": job.reason_code,
        "reconciliation_required": job.reconciliation_required,
    }


@router.get("/jobs")
def list_jobs(
    op: Annotated[Operator, Depends(admin)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """Read one newest-first page of the requesting administrator's jobs."""
    owner_filter = ProvisioningJob.requester_id == op.id
    total = db.scalar(
        select(func.count()).select_from(ProvisioningJob).where(owner_filter)
    )
    jobs = db.scalars(
        select(ProvisioningJob)
        .where(owner_filter)
        .order_by(ProvisioningJob.created_at.desc(), ProvisioningJob.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {"jobs": [job_metadata(job) for job in jobs], "total": total or 0}


@router.get("/jobs/{job_id}")
def job_status(
    job_id: str,
    op: Annotated[Operator, Depends(admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    job = db.get(ProvisioningJob, job_id)
    if job is None or job.requester_id != op.id:
        raise HTTPException(404, "JOB_NOT_FOUND")
    events = db.scalars(
        select(ProvisioningEvent)
        .where(ProvisioningEvent.job_id == job.id)
        .order_by(ProvisioningEvent.sequence)
    ).all()
    return {
        **job_metadata(job),
        "retry_allowed": job.state == "FAILED"
        and not job.reconciliation_required
        and job.step == "REVALIDATE",
        "events": [
            {
                "sequence": e.sequence,
                "code": e.code,
                "at": e.at,
                "safe_detail": safe_event_detail(e),
            }
            for e in events
        ],
    }


def safe_event_detail(event: ProvisioningEvent) -> dict[str, int]:
    """Explicit allowlist: never expose arbitrary provider text or stored JSON."""
    if event.code not in {
        "INSTALL_COMPLETED", "INSTALL_TIMED_OUT", "INSTALL_CANCELLED",
        "INSTALL_TRANSPORT_FAILED",
    }:
        return {}
    try:
        detail = json.loads(event.safe_detail_json or "{}")
    except (ValueError, TypeError):
        return {}
    if not isinstance(detail, dict):
        return {}
    result = {}
    for key in ("installer_exit_status", "transport_exit_status"):
        status = detail.get(key)
        # Negative transport statuses exist in legacy failure events only.
        minimum = -255 if key == "transport_exit_status" and event.code == "INSTALL_TRANSPORT_FAILED" else 0
        if type(status) is int and minimum <= status <= 255:
            result[key] = status
    return result


@router.post("/jobs/{job_id}/retry")
def retry(
    job_id: str,
    op: Annotated[Operator, Depends(admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    try:
        target_id = retry_plan(db, job_id, op.id)
    except ValueError:
        raise HTTPException(409, "UNSAFE_RETRY_REQUIRES_RECONCILIATION") from None
    return {"target_id": target_id, "next": "PREFLIGHT_AND_CONFIRM_REQUIRED"}
