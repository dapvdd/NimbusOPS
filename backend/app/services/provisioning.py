"""Durable plans and atomic confirmation using the existing provisioning schema."""

import hashlib
import json
import time
from dataclasses import asdict
from uuid import uuid4

from sqlalchemy import false, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Host
from ..models.provisioning import (
    ProvisioningConnection,
    ProvisioningEvent,
    ProvisioningJob,
    ProvisioningOwnership,
    ProvisioningRequest,
    ProvisioningTarget,
    ProvisioningValidation,
)
from ..provisioning.ssh import Target


def now_ms() -> int:
    return int(time.time() * 1000)


def policy_hash(target: Target) -> str:
    return hashlib.sha256(
        json.dumps(asdict(target), sort_keys=True).encode()
    ).hexdigest()


def save_plan(
    db: Session, actor_id: str, target: Target, facts: dict[str, str]
) -> ProvisioningValidation:
    """Persist reviewed facts, never credentials or credential references."""
    if db.scalar(select(Host).where(Host.hostname == target.hostname)):
        raise ValueError("EXISTING_HOST_IDENTITY")
    connection = db.get(ProvisioningConnection, target.id)
    digest = policy_hash(target)
    if connection is None:
        connection = ProvisioningConnection(
            id=target.id,
            provider="GENERIC_LINUX",
            display_name=target.id,
            policy_hash=digest,
            enabled=True,
        )
        db.add(connection)
        db.flush()
    connection.policy_hash = digest
    row = db.get(ProvisioningTarget, target.id)
    if row is None:
        row = ProvisioningTarget(
            id=target.id,
            connection_id=target.id,
            canonical_key="ssh-machine:" + target.machine_id,
            discovered_at=now_ms(),
        )
        db.add(row)
        db.flush()
    if row.canonical_key != "ssh-machine:" + target.machine_id:
        raise ValueError("TARGET_BINDING_CHANGED")
    plan_json = json.dumps(
        {
            "facts": facts,
            "policy_hash": digest,
            "hostname": target.hostname,
            "mode": "telemetry-only",
        },
        sort_keys=True,
    )
    plan = ProvisioningValidation(
        target_id=row.id,
        actor_id=actor_id,
        plan_json=plan_json,
        plan_hash=hashlib.sha256(plan_json.encode()).hexdigest(),
        config_revision=1,
        mapping_revision=0,
        observed_identity_hash=hashlib.sha256(target.machine_id.encode()).hexdigest(),
        created_at=now_ms(),
        expires_at=now_ms() + 300_000,
    )
    db.add(plan)
    db.commit()
    return plan


def confirmation_hash(target_id: str, validation_id: str, approval_hash: str) -> str:
    return hashlib.sha256(
        json.dumps([target_id, validation_id, approval_hash]).encode()
    ).hexdigest()


def recover_confirmation(
    db: Session, actor_id: str, key: str, request_hash: str | None = None
) -> ProvisioningJob | None:
    request = db.get(ProvisioningRequest, (actor_id, "ssh-confirm", key))
    if request is None:
        return None
    if request_hash is not None and request.request_hash != request_hash:
        raise ValueError("IDEMPOTENCY_KEY_CONFLICT")
    job = db.get(ProvisioningJob, request.job_id)
    if job is None or job.requester_id != actor_id:
        raise ValueError("JOB_NOT_FOUND")
    return job


def confirm_plan(
    db: Session,
    actor_id: str,
    target: Target,
    validation_id: str,
    approval_hash: str,
    *,
    idempotency_key: str | None = None,
) -> ProvisioningJob:
    """One-shot approval and exclusive target reservation in one transaction."""
    digest = confirmation_hash(target.id, validation_id, approval_hash)
    if idempotency_key is not None:
        recovered = recover_confirmation(db, actor_id, idempotency_key, digest)
        if recovered is not None:
            return recovered
    db.execute(
        update(ProvisioningOwnership)
        .where(false())
        .values(generation=ProvisioningOwnership.generation)
    )
    if idempotency_key is not None:
        recovered = recover_confirmation(db, actor_id, idempotency_key, digest)
        if recovered is not None:
            return recovered
    plan = db.get(ProvisioningValidation, validation_id)
    if (
        plan is None
        or plan.actor_id != actor_id
        or plan.target_id != target.id
        or plan.expires_at <= now_ms()
        or plan.plan_hash != approval_hash
        or plan.consumed_by_job_id is not None
        or json.loads(plan.plan_json)["policy_hash"] != policy_hash(target)
    ):
        raise ValueError("APPROVAL_INVALID_OR_EXPIRED")
    if db.scalar(select(Host).where(Host.hostname == target.hostname)):
        raise ValueError("EXISTING_HOST_IDENTITY")
    job_id = str(uuid4())
    from .enrollment import check_onboarding_ownership, normalize_hostname
    from ..core.errors import ApiError

    try:
        check_onboarding_ownership(db, normalize_hostname(target.hostname))
    except ApiError:
        raise ValueError("TARGET_ALREADY_RESERVED") from None
    claimed = db.execute(
        update(ProvisioningValidation)
        .where(
            ProvisioningValidation.id == plan.id,
            ProvisioningValidation.consumed_by_job_id.is_(None),
            ProvisioningValidation.expires_at > now_ms(),
        )
        .values(consumed_by_job_id=job_id)
    )
    if claimed.rowcount != 1:
        db.rollback()
        if idempotency_key is not None:
            recovered = recover_confirmation(db, actor_id, idempotency_key, digest)
            if recovered is not None:
                return recovered
        raise ValueError("APPROVAL_ALREADY_CONSUMED")
    stamp = now_ms()
    job = ProvisioningJob(
        id=job_id,
        target_id=target.id,
        operation="INSTALL",
        validation_id=plan.id,
        requester_id=actor_id,
        approval_hash=approval_hash,
        approved_at=stamp,
        approval_expires_at=plan.expires_at,
        plan_json=plan.plan_json,
        deadline_at=stamp + 900_000,
        created_at=stamp,
        updated_at=stamp,
    )
    db.add(job)
    if idempotency_key is not None:
        db.add(
            ProvisioningRequest(
                actor_id=actor_id,
                route_scope="ssh-confirm",
                idempotency_key=idempotency_key,
                request_hash=digest,
                job_id=job_id,
            )
        )
    ownership = db.get(ProvisioningOwnership, target.id)
    if ownership is None:
        db.add(
            ProvisioningOwnership(
                target_id=target.id, owner_job_id=job_id, acquired_at=stamp
            )
        )
    else:
        reserved = db.execute(
            update(ProvisioningOwnership)
            .where(
                ProvisioningOwnership.target_id == target.id,
                ProvisioningOwnership.disposition == "RELEASED",
            )
            .values(
                owner_job_id=job_id,
                disposition="HELD",
                generation=ProvisioningOwnership.generation + 1,
                acquired_at=stamp,
                released_at=None,
            )
        )
        if reserved.rowcount != 1:
            db.rollback()
            raise ValueError("TARGET_ALREADY_RESERVED")
    db.add(
        ProvisioningEvent(
            job_id=job_id,
            sequence=1,
            at=stamp,
            actor_kind="OPERATOR",
            actor_id=actor_id,
            code="INSTALL_APPROVED",
            state="PENDING",
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key is not None:
            recovered = recover_confirmation(db, actor_id, idempotency_key, digest)
            if recovered is not None:
                return recovered
        raise ValueError("TARGET_ALREADY_RESERVED") from None
    return job


def retry_plan(db: Session, job_id: str, actor_id: str) -> str:
    """Release only a proven pre-dispatch failure; require new preflight/approval.

    Admitted/unknown outcomes are deliberately not automatically recoverable.
    """
    job = db.get(ProvisioningJob, job_id)
    if (
        job is None
        or job.requester_id != actor_id
        or job.state != "FAILED"
        or job.reconciliation_required
        or job.step != "REVALIDATE"
        or "bootstrap_token_id" in json.loads(job.plan_json)
    ):
        raise ValueError("UNSAFE_RETRY_REQUIRES_RECONCILIATION")
    ownership = db.get(ProvisioningOwnership, job.target_id)
    if ownership is None or ownership.owner_job_id != job.id:
        raise ValueError("OWNERSHIP_CHANGED")
    # Keep ownership history. confirm_plan reuses released rows atomically.
    if not release_for_retry(db, job.target_id, job.id, ownership.generation):
        db.rollback()
        raise ValueError("OWNERSHIP_CHANGED")
    db.commit()
    return job.target_id


def release_for_retry(
    db: Session, target_id: str, job_id: str, generation: int
) -> bool:
    result = db.execute(
        update(ProvisioningOwnership)
        .where(
            ProvisioningOwnership.target_id == target_id,
            ProvisioningOwnership.owner_job_id == job_id,
            ProvisioningOwnership.generation == generation,
            ProvisioningOwnership.disposition == "HELD",
        )
        .values(disposition="RELEASED", released_at=now_ms())
    )
    return result.rowcount == 1
