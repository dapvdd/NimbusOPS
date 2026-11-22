"""Separate opt-in worker: python -m backend.app.provisioning.worker.

Claimed installs are never dispatched twice. A restart reconciles token-linked
telemetry; uncertain outcomes retain ownership and require operator inspection.
"""

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..core.db import SessionLocal
from ..core.errors import ApiError
from ..models import BootstrapToken, Host, Operator, Telemetry
from ..models.provisioning import (
    ProvisioningEvent,
    ProvisioningJob,
    ProvisioningOwnership,
)
from ..services.enrollment import issue_bootstrap_token
from ..services.provisioning import now_ms, policy_hash
from .ssh import InstallOutcomeUnknown, Target, install, preflight


def claim_job(db: Session) -> str | None:
    """CAS admission: commit uncertainty before any remote side effect."""
    job_id = db.scalar(
        select(ProvisioningJob.id)
        .where(ProvisioningJob.state == "PENDING")
        .order_by(ProvisioningJob.created_at)
        .limit(1)
    )
    if job_id is None:
        return None
    result = db.execute(
        update(ProvisioningJob)
        .where(ProvisioningJob.id == job_id, ProvisioningJob.state == "PENDING")
        .values(state="RUNNING", reconciliation_required=True, updated_at=now_ms())
    )
    db.commit()
    return job_id if result.rowcount == 1 else None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def enrollment_ready(db: Session, token_id: str) -> bool:
    """Require this installation's consumed token, heartbeat and real telemetry."""
    token = db.get(BootstrapToken, token_id)
    if token is None or token.consumed_at is None or token.consumed_by is None:
        return False
    host = db.get(Host, token.consumed_by)
    if (
        host is None
        or host.is_revoked
        or host.docker_enabled
        or host.hostname != token.hostname
    ):
        return False
    latest = db.scalar(
        select(func.max(Telemetry.recorded_at)).where(Telemetry.host_id == host.id)
    )
    now = datetime.now(UTC)
    consumed_at = _utc(token.consumed_at)

    def fresh(value: datetime | None) -> bool:
        return (
            value is not None
            and consumed_at <= _utc(value) <= now
            and (now - _utc(value)).total_seconds() <= 90
        )

    return all(fresh(v) for v in (host.last_seen_at, host.last_telemetry_at, latest))


def event(
    db: Session,
    job: ProvisioningJob,
    code: str,
    safe_detail: dict[str, int] | None = None,
) -> None:
    sequence = (
        db.scalar(
            select(func.max(ProvisioningEvent.sequence)).where(
                ProvisioningEvent.job_id == job.id
            )
        )
        or 0
    ) + 1
    db.add(
        ProvisioningEvent(
            job_id=job.id,
            sequence=sequence,
            at=now_ms(),
            actor_kind="WORKER",
            actor_id="ssh-worker",
            code=code,
            state=job.state,
            safe_detail_json=(
                json.dumps(safe_detail) if safe_detail is not None else None
            ),
        )
    )
    job.updated_at = now_ms()
    db.commit()


@contextmanager
def worker_lock(database: str) -> Iterator[bool]:
    """Single-host SQLite worker lock covers dispatch AND reconciliation.

    Kernel lock releases on crash; all workers must use the same database path.
    Supported deployment is SQLite on local storage, not distributed workers.
    """
    import hashlib
    import tempfile

    lock_path = Path(tempfile.gettempdir()) / (
        "nimbusops-worker-" + hashlib.sha256(database.encode()).hexdigest() + ".lock"
    )
    with lock_path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        locked = False
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import importlib

                fcntl = importlib.import_module("fcntl")

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError:
            pass
        try:
            yield locked
        finally:
            if locked:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def run_once(db: Session, targets: dict[str, Target], origin: str) -> None:
    bind = db.get_bind()
    from sqlalchemy.engine import Engine

    database = str(bind.url if isinstance(bind, Engine) else bind.engine.url)
    with worker_lock(database) as acquired:
        if acquired:
            _run_once(db, targets, origin)


def _run_once(db: Session, targets: dict[str, Target], origin: str) -> None:
    """Dispatch one new install, then reconcile all admitted jobs without retry."""
    job_id = claim_job(db)
    if job_id:
        job = db.get(ProvisioningJob, job_id)
        assert job is not None
        target = targets.get(job.target_id)
        try:
            if target is None or job.approval_expires_at <= now_ms():
                raise ValueError("AUTHORIZATION_EXPIRED")
            plan = json.loads(job.plan_json)
            if plan["policy_hash"] != policy_hash(target):
                raise ValueError("POLICY_CHANGED")
            facts = preflight(target)
            if facts != plan["facts"]:
                raise ValueError("TARGET_CHANGED")
            if db.scalar(select(Host.id).where(Host.hostname == target.hostname)):
                raise ValueError("EXISTING_IDENTITY")
            actor = db.get(Operator, job.requester_id)
            if actor is None or actor.role != "ADMIN":
                raise ValueError("ADMIN_AUTHORIZATION_REVOKED")
            owner = db.get(ProvisioningOwnership, job.target_id)
            if owner is None or owner.owner_job_id != job.id:
                raise ValueError("OWNERSHIP_CHANGED")
            plan["ownership_generation"] = owner.generation
            token, plaintext = issue_bootstrap_token(
                db,
                actor,
                target.hostname,
                600,
                commit=False,
                provisioning_job_id=job.id,
                ownership_generation=owner.generation,
            )
            plan["bootstrap_token_id"] = token.id
            job.plan_json = json.dumps(plan)
            job.step = "INSTALL_ADMITTED"
            event(db, job, "INSTALL_ADMITTED")
            install(target, origin, plaintext)
            del plaintext
            job.state = "VERIFYING"
            event(db, job, "WAITING_FOR_TELEMETRY")
        except (ValueError, ApiError) as exc:
            if job.step == "REVALIDATE" and "bootstrap_token_id" not in json.loads(
                job.plan_json
            ):
                job.reason_code = "PREFLIGHT_REJECTED"
                job.state = "FAILED"
                job.reconciliation_required = False
                job.completed_at = now_ms()
                event(db, job, "PREFLIGHT_REJECTED")
            else:
                job.reason_code = "RECONCILIATION_REQUIRED"
                job.state = "VERIFYING"
                if (
                    isinstance(exc, InstallOutcomeUnknown)
                    and exc.exit_status is not None
                ):
                    event(
                        db,
                        job,
                        "INSTALL_TRANSPORT_FAILED",
                        {"transport_exit_status": exc.exit_status},
                    )
                event(db, job, "RECONCILIATION_REQUIRED")
        except Exception:
            # Do not log provider output/credentials. A committed admission is
            # deliberately retained for the next reconciliation pass.
            db.rollback()
            raise
    for job in db.scalars(
        select(ProvisioningJob).where(
            ProvisioningJob.state.in_(("RUNNING", "VERIFYING"))
        )
    ).all():
        token_id = json.loads(job.plan_json).get("bootstrap_token_id")
        if token_id and enrollment_ready(db, token_id):
            job.state = "SUCCEEDED"
            job.reconciliation_required = False
            job.completed_at = now_ms()
            event(db, job, "FRESH_TELEMETRY_VERIFIED")
        elif job.deadline_at <= now_ms():
            job.state = "FAILED"
            job.reason_code = "RECONCILIATION_REQUIRED"
            job.completed_at = now_ms()
            event(db, job, "DEADLINE_EXCEEDED")


def main() -> None:
    from ..api.provisioning import configured_targets

    origin = os.environ["NIMBUSOPS_PROVISIONING_ORIGIN"]
    while True:
        with SessionLocal() as db:
            run_once(db, configured_targets(), origin)
        time.sleep(5)


if __name__ == "__main__":
    main()
