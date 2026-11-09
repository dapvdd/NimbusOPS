"""Deployment domain logic: templates, operations, command claim/delivery.

Semantics pinned here (single source of truth):
- One deployment per (host, template): redeploy reuses it (idempotent).
- One in-flight (QUEUED/RUNNING) operation per deployment: a deploy request
  while one is in flight returns the SAME operation (deduplicated=true).
- SUCCEEDED requires agent-reported verifiable evidence (result payload);
  the backend never fabricates success.
- Commands are claimed exactly once (atomic status flip QUEUED->RUNNING).
- Results are first-write-wins; duplicate deliveries are acknowledged as
  accepted=false (idempotent), never re-executed.
- Terminal ops (SUCCEEDED/FAILED/UNKNOWN) are not re-claimed on poll.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..core.codes import ErrorCode
from ..core.errors import ApiError
from ..models import DeploymentOperation, DeploymentTemplate, Host, ManagedDeployment, OperationEvent
from ..schemas import AgentCommand, DeployRequest, OperationOut

logger = logging.getLogger("nimbusops.deployments")

IN_FLIGHT = ("QUEUED", "RUNNING")
TERMINAL = ("SUCCEEDED", "FAILED", "UNKNOWN")

OP_TYPES = ("DEPLOY", "START", "STOP")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_host_or_404(db: Session, host_id: str) -> Host:
    host = db.get(Host, host_id)
    if host is None:
        raise ApiError(404, ErrorCode.HOST_NOT_FOUND, f"host {host_id} not found")
    return host


def _get_deployment_or_404(db: Session, deployment_id: str) -> ManagedDeployment:
    dep = db.get(ManagedDeployment, deployment_id)
    if dep is None:
        raise ApiError(404, ErrorCode.DEPLOYMENT_NOT_FOUND, f"deployment {deployment_id} not found")
    return dep


# ----------------------------------------------------------------- templates


def seed_templates(db: Session) -> None:
    """Idempotently seed the approved template catalog."""
    approved = [
        {
            "key": "nginx-demo",
            "name": "Nginx Demo",
            "description": "Deterministic single-container Nginx serving the default page.",
            "image": "nginx:1.27-alpine",
            "container_port": 80,
            "host_port": 18080,
            "is_approved": True,
        },
    ]
    for t in approved:
        if db.get(DeploymentTemplate, t["key"]) is None:
            db.add(DeploymentTemplate(**t))
    db.commit()


def list_templates(db: Session) -> list[DeploymentTemplate]:
    return list(
        db.scalars(
            select(DeploymentTemplate)
            .where(DeploymentTemplate.is_approved)
            .order_by(DeploymentTemplate.key)
        ).all()
    )


def _get_template_or_422(db: Session, key: str) -> DeploymentTemplate:
    tmpl = db.get(DeploymentTemplate, key)
    if tmpl is None or not tmpl.is_approved:
        raise ApiError(422, ErrorCode.INVALID_TEMPLATE, f"template {key!r} is not an approved template")
    return tmpl


# ------------------------------------------------------------- deployments


def app_url_for(tmpl: DeploymentTemplate) -> str:
    """Deterministic URL where the deployed app is reachable.

    Phase 2 scope: single-host, fixed host port per template; operator and
    control server share the machine in this MVP.
    """
    return f"http://localhost:{tmpl.host_port}/"


def _container_name(host: Host, tmpl: DeploymentTemplate) -> str:
    """Deterministic, label-verified container name (no collisions with
    unrelated containers: NimbusOps names always carry the prefix)."""
    return f"nimbusops-{tmpl.key}-{host.id[:8]}"


def _latest_op(db: Session, deployment_id: str) -> DeploymentOperation | None:
    return db.scalar(
        select(DeploymentOperation)
        .where(DeploymentOperation.deployment_id == deployment_id)
        .order_by(DeploymentOperation.created_at.desc(), DeploymentOperation.id.desc())
        .limit(1)
    )


def _op_out(op: DeploymentOperation) -> OperationOut:
    result = None
    if op.result_json:
        try:
            result = json.loads(op.result_json)
        except json.JSONDecodeError:
            result = None
    return OperationOut(
        id=op.id,
        deployment_id=op.deployment_id,
        host_id=op.host_id,
        op_type=op.op_type,
        status=op.status,
        created_at=op.created_at,
        updated_at=op.updated_at,
        completed_at=op.completed_at,
        result=result,
        error_code=op.error_code,
        error_message=op.error_message,
    )


def create_deployment(db: Session, req: DeployRequest) -> tuple[ManagedDeployment, DeploymentOperation, bool]:
    """Create (or reuse) the (host, template) deployment; return (dep, op, dedup).

    Duplicate protection: an in-flight (QUEUED/RUNNING) operation for the same
    deployment is returned as-is instead of creating a duplicate.
    """
    host = _get_host_or_404(db, req.host_id)
    tmpl = _get_template_or_422(db, req.template_key)

    dep = db.scalar(
        select(ManagedDeployment).where(
            ManagedDeployment.host_id == host.id,
            ManagedDeployment.template_key == tmpl.key,
        )
    )
    if dep is None:
        dep = ManagedDeployment(
            host_id=host.id,
            template_key=tmpl.key,
            container_name=_container_name(host, tmpl),
        )
        db.add(dep)
        db.flush()

    inflight = db.scalar(
        select(DeploymentOperation)
        .where(
            DeploymentOperation.deployment_id == dep.id,
            DeploymentOperation.status.in_(IN_FLIGHT),
        )
        .order_by(DeploymentOperation.created_at.desc())
        .limit(1)
    )
    if inflight is not None:
        return dep, inflight, True

    op = DeploymentOperation(
        deployment_id=dep.id,
        host_id=host.id,
        op_type="DEPLOY",
        status="QUEUED",
    )
    db.add(op)
    db.flush()
    db.add(
        OperationEvent(
            operation_id=op.id, event="CREATED", detail=f"template={tmpl.key} host={host.hostname}"
        )
    )
    db.commit()
    return dep, op, False


def create_lifecycle_operation(db: Session, deployment_id: str, op_type: str) -> tuple[ManagedDeployment, DeploymentOperation, bool]:
    """Queue START or STOP for an existing deployment (same dedup rules)."""
    if op_type not in ("START", "STOP"):
        raise ApiError(422, ErrorCode.INVALID_OPERATION, f"op_type {op_type!r} not permitted")
    dep = _get_deployment_or_404(db, deployment_id)

    inflight = db.scalar(
        select(DeploymentOperation)
        .where(
            DeploymentOperation.deployment_id == dep.id,
            DeploymentOperation.status.in_(IN_FLIGHT),
        )
        .order_by(DeploymentOperation.created_at.desc())
        .limit(1)
    )
    if inflight is not None:
        return dep, inflight, True

    op = DeploymentOperation(
        deployment_id=dep.id,
        host_id=dep.host_id,
        op_type=op_type,
        status="QUEUED",
    )
    db.add(op)
    db.flush()
    db.add(OperationEvent(operation_id=op.id, event="CREATED", detail=f"deployment={dep.id}"))
    db.commit()
    return dep, op, False


# --------------------------------------------------------- agent command API


def poll_commands(db: Session, host_id: str, limit: int = 8) -> list[AgentCommand]:
    """Atomically claim QUEUED ops for this host: QUEUED -> RUNNING.

    A claimed op is delivered exactly once (claim is part of delivery);
    disconnected agents pick work up on their next poll. Terminal ops are
    never re-delivered.
    """
    now = _utcnow()
    queued_ids = db.scalars(
        select(DeploymentOperation.id)
        .where(DeploymentOperation.host_id == host_id, DeploymentOperation.status == "QUEUED")
        .order_by(DeploymentOperation.created_at.asc())
        .limit(limit)
    ).all()
    claimed: list[AgentCommand] = []
    for op_id in queued_ids:
        # Atomic claim: UPDATE ... WHERE status='QUEUED' guards against
        # double-delivery across concurrent pollers.
        updated = db.execute(
            update(DeploymentOperation)
            .where(DeploymentOperation.id == op_id, DeploymentOperation.status == "QUEUED")
            .values(status="RUNNING", claimed_at=now, updated_at=now)
        )
        if updated.rowcount == 1:
            db.add(OperationEvent(operation_id=op_id, event="CLAIMED", detail=f"host={host_id}"))
            op = db.get(DeploymentOperation, op_id)
            cmd = AgentCommand(**_op_out(op).model_dump())
            # Template payload rides on EVERY op type: the agent needs
            # container_name to act (DEPLOY runs it; START/STOP address it).
            # Phase 2 attached it only for DEPLOY, so real START/STOP failed
            # with UNAPPROVED_OPERATION ("container name '' outside managed
            # prefix") — caught in Stage B live validation.
            dep = db.get(ManagedDeployment, op.deployment_id)
            tmpl = db.get(DeploymentTemplate, dep.template_key)
            cmd.template = {
                "key": tmpl.key,
                "image": tmpl.image,
                "container_port": tmpl.container_port,
                "host_port": tmpl.host_port,
                "container_name": dep.container_name,
            }
            claimed.append(cmd)
    db.commit()
    return claimed


def submit_result(
    db: Session, host_id: str, operation_id: str, req  # CommandResultRequest
) -> tuple[DeploymentOperation, bool]:
    """Record the agent's result. First write wins; duplicates are accepted
    with accepted=False and never overwrite existing evidence."""
    op = db.get(DeploymentOperation, operation_id)
    if op is None:
        raise ApiError(404, ErrorCode.OPERATION_NOT_FOUND, f"operation {operation_id} not found")
    if op.host_id != host_id:
        raise ApiError(403, ErrorCode.FORBIDDEN_HOST, "operation belongs to another host")
    if op.status in TERMINAL:
        # Idempotent redelivery: keep original evidence.
        return op, False
    op.status = req.status
    op.completed_at = _utcnow()
    op.updated_at = op.completed_at
    if req.result is not None:
        op.result_json = json.dumps(req.result)[:2048]
    op.error_code = req.error_code
    op.error_message = (req.error_message or "")[:512] or None
    db.add(OperationEvent(operation_id=op.id, event="RESULT", detail=f"status={req.status}"))
    db.commit()
    return op, True


def get_operation(db: Session, operation_id: str) -> DeploymentOperation:
    op = db.get(DeploymentOperation, operation_id)
    if op is None:
        raise ApiError(404, ErrorCode.OPERATION_NOT_FOUND, f"operation {operation_id} not found")
    return op


# ------------------------------------------------------------- app inventory


def _reported_state(op: DeploymentOperation | None) -> tuple[str | None, bool | None, datetime | None]:
    """Extract agent-reported container state from the most recent op with evidence."""
    if op is None or not op.result_json:
        return None, None, None
    try:
        result = json.loads(op.result_json)
    except json.JSONDecodeError:
        return None, None, None
    state = result.get("container_state")
    http_ok = result.get("http_ok")
    if not isinstance(state, str):
        state = None
    if not isinstance(http_ok, bool):
        http_ok = None
    return state, http_ok, op.completed_at or op.updated_at


def list_managed_apps(db: Session) -> list[dict]:
    """Managed application inventory with honest unknown-when-unreported state."""
    rows = db.execute(
        select(ManagedDeployment, Host, DeploymentTemplate)
        .join(Host, ManagedDeployment.host_id == Host.id)
        .join(DeploymentTemplate, ManagedDeployment.template_key == DeploymentTemplate.key)
        .order_by(ManagedDeployment.created_at.asc())
    ).all()
    apps = []
    for dep, host, tmpl in rows:
        last_op = _latest_op(db, dep.id)
        state, http_ok, reported_at = _reported_state(last_op)
        apps.append(
            {
                "deployment_id": dep.id,
                "host_id": host.id,
                "hostname": host.hostname,
                "template_key": dep.template_key,
                "container_name": dep.container_name,
                "app_url": app_url_for(tmpl),
                "last_operation": _op_out(last_op) if last_op else None,
                "container_state": state,
                "http_ok": http_ok,
                "reported_at": reported_at,
            }
        )
    return apps


def get_container_state(db: Session, deployment_id: str) -> dict:
    """Actual container state as last reported by the agent (never fabricated)."""
    dep = _get_deployment_or_404(db, deployment_id)
    tmpl = db.get(DeploymentTemplate, dep.template_key)
    last_op = _latest_op(db, dep.id)
    state, http_ok, reported_at = _reported_state(last_op)
    if state is None:
        state = "NOT_REPORTED"
    return {
        "deployment_id": dep.id,
        "container_state": state,
        "http_ok": http_ok,
        "reported_at": reported_at,
        "container_name": dep.container_name,
        "app_url": app_url_for(tmpl) if tmpl else f"http://localhost:8080/",
    }
