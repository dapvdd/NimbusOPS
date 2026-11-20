"""ADMIN-only target discovery. Server policy is the authorization boundary."""

import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import Operator
from ..models.provisioning import ProvisioningEvent, ProvisioningJob
from ..provisioning.ssh import Target, load_targets, preflight
from ..services.provisioning import confirm_plan, retry_plan, save_plan
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
def targets(op: Operator = Depends(admin)) -> dict[str, Any]:
    return {
        "targets": [
            {"id": t.id, "hostname": t.hostname, "address": t.address}
            for t in configured_targets().values()
        ]
    }


@router.post("/preflight")
def inspect_target(
    req: PreflightRequest, op: Operator = Depends(admin), db: Session = Depends(get_db)
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


@router.post("/confirm", status_code=202)
def confirm(
    req: ConfirmRequest, op: Operator = Depends(admin), db: Session = Depends(get_db)
) -> dict[str, str]:
    target = configured_targets().get(req.target_id)
    if target is None:
        raise HTTPException(404, "TARGET_NOT_AUTHORIZED")
    try:
        job = confirm_plan(db, op.id, target, req.validation_id, req.approval_hash)
    except ValueError:
        db.rollback()
        raise HTTPException(409, "APPROVAL_INVALID_OR_TARGET_RESERVED") from None
    return {"id": job.id, "state": job.state}


@router.get("/jobs/{job_id}")
def job_status(
    job_id: str, op: Operator = Depends(admin), db: Session = Depends(get_db)
) -> dict[str, Any]:
    job = db.get(ProvisioningJob, job_id)
    if job is None:
        raise HTTPException(404, "JOB_NOT_FOUND")
    events = db.scalars(
        select(ProvisioningEvent)
        .where(ProvisioningEvent.job_id == job.id)
        .order_by(ProvisioningEvent.sequence)
    ).all()
    return {
        "id": job.id,
        "state": job.state,
        "step": job.step,
        "reason_code": job.reason_code,
        "reconciliation_required": job.reconciliation_required,
        "retry_allowed": job.state == "FAILED"
        and not job.reconciliation_required
        and job.step == "REVALIDATE",
        "events": [
            {"sequence": e.sequence, "code": e.code, "at": e.at} for e in events
        ],
    }


@router.post("/jobs/{job_id}/retry")
def retry(
    job_id: str, op: Operator = Depends(admin), db: Session = Depends(get_db)
) -> dict[str, str]:
    try:
        target_id = retry_plan(db, job_id, op.id)
    except ValueError:
        raise HTTPException(409, "UNSAFE_RETRY_REQUIRES_RECONCILIATION") from None
    return {"target_id": target_id, "next": "PREFLIGHT_AND_CONFIRM_REQUIRED"}
