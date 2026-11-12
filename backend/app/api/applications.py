"""Applications API (browser-facing): templates, deploy, lifecycle, state.

Phase 3B: mutating application endpoints require an operator session (AC-01);
Docker-touching operations additionally require `docker_enabled=true` on the
target host (Docker default-off, contract §6). Read endpoints remain
unauthenticated (trusted-local model, Phase 3B scope).
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.codes import ErrorCode
from ..core.db import get_db
from ..core.errors import ApiError
from ..models import DeploymentTemplate, Host, OperationEvent
from ..schemas import (
    ContainerStateResponse,
    DeployRequest,
    DeployResponse,
    ManagedAppListResponse,
    OperationEventOut,
    OperationEventsResponse,
    OperationListResponse,
    OperationOut,
    TemplateListResponse,
)
from ..services import deployments as svc
from .operators import require_operator

router = APIRouter(prefix="/api/v1")


def _require_docker_enabled(db: Session, host_id: str) -> Host:
    host = db.get(Host, host_id)
    if host is None:
        raise ApiError(404, ErrorCode.HOST_NOT_FOUND, f"host {host_id} not found")
    if not host.docker_enabled:
        raise ApiError(
            403,
            ErrorCode.DOCKER_NOT_AUTHORIZED,
            "docker operations are disabled for this host; an operator must enable them",
        )
    return host


def _op_response(db: Session, dep, op, dedup: bool) -> DeployResponse:
    tmpl = db.get(DeploymentTemplate, dep.template_key)
    return DeployResponse(
        operation_id=op.id,
        deployment_id=dep.id,
        host_id=dep.host_id,
        template_key=dep.template_key,
        status=op.status,
        container_name=dep.container_name,
        app_url=svc.app_url_for(tmpl),
        deduplicated=dedup,
        op_type=op.op_type,
    )


@router.get("/templates", response_model=TemplateListResponse)
def list_templates(db: Session = Depends(get_db)) -> TemplateListResponse:
    templates = svc.list_templates(db)
    items = []
    for t in templates:
        items.append(
            {
                "key": t.key,
                "name": t.name,
                "description": t.description,
                "image": t.image,
                "container_port": t.container_port,
                "host_port": t.host_port,
                "is_approved": t.is_approved,
            }
        )
    return TemplateListResponse(templates=items)


@router.get("/applications", response_model=ManagedAppListResponse)
def list_applications(db: Session = Depends(get_db)) -> ManagedAppListResponse:
    apps = svc.list_managed_apps(db)
    return ManagedAppListResponse(applications=apps, count=len(apps))


@router.post("/applications/deploy", response_model=DeployResponse, status_code=202)
def deploy(
    req: DeployRequest,
    op: object = Depends(require_operator(role="ADMIN")),
    db: Session = Depends(get_db),
) -> DeployResponse:
    _require_docker_enabled(db, req.host_id)
    dep, op_row, dedup = svc.create_deployment(db, req)
    return _op_response(db, dep, op_row, dedup)


@router.post("/applications/{deployment_id}/start", response_model=DeployResponse, status_code=202)
def start_app(
    deployment_id: str,
    op: object = Depends(require_operator(role="ADMIN")),
    db: Session = Depends(get_db),
) -> DeployResponse:
    dep = svc._get_deployment_or_404(db, deployment_id)
    _require_docker_enabled(db, dep.host_id)
    dep, op_row, dedup = svc.create_lifecycle_operation(db, deployment_id, "START")
    return _op_response(db, dep, op_row, dedup)


@router.post("/applications/{deployment_id}/stop", response_model=DeployResponse, status_code=202)
def stop_app(
    deployment_id: str,
    op: object = Depends(require_operator(role="ADMIN")),
    db: Session = Depends(get_db),
) -> DeployResponse:
    dep = svc._get_deployment_or_404(db, deployment_id)
    _require_docker_enabled(db, dep.host_id)
    dep, op_row, dedup = svc.create_lifecycle_operation(db, deployment_id, "STOP")
    return _op_response(db, dep, op_row, dedup)


@router.post("/applications/{deployment_id}/restart", response_model=DeployResponse, status_code=202)
def restart_app(
    deployment_id: str,
    op: object = Depends(require_operator(role="ADMIN")),
    db: Session = Depends(get_db),
) -> DeployResponse:
    """Phase 5: queue a RESTART for the deployment's managed container."""
    dep = svc._get_deployment_or_404(db, deployment_id)
    _require_docker_enabled(db, dep.host_id)
    dep, op_row, dedup = svc.create_lifecycle_operation(db, deployment_id, "RESTART")
    return _op_response(db, dep, op_row, dedup)


@router.get("/applications/{deployment_id}/container-state", response_model=ContainerStateResponse)
def container_state(deployment_id: str, db: Session = Depends(get_db)) -> ContainerStateResponse:
    return ContainerStateResponse(**svc.get_container_state(db, deployment_id))


@router.get("/operations/{operation_id}", response_model=OperationOut)
def read_operation(operation_id: str, db: Session = Depends(get_db)) -> OperationOut:
    return svc._op_out(svc.get_operation(db, operation_id))


# ------------------------------------------------- Phase 5 (FR-08): history


@router.get("/operations", response_model=OperationListResponse)
def list_operations(
    host_id: str | None = Query(default=None, max_length=36),
    status: str | None = Query(default=None, max_length=16),
    deployment_id: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> OperationListResponse:
    """Operation history: filtered, bounded, deterministic (created ASC)."""
    from ..models import DeploymentOperation

    stmt = select(DeploymentOperation).order_by(
        DeploymentOperation.created_at.asc(), DeploymentOperation.id.asc()
    )
    if host_id is not None:
        stmt = stmt.where(DeploymentOperation.host_id == host_id)
    if deployment_id is not None:
        stmt = stmt.where(DeploymentOperation.deployment_id == deployment_id)
    if status is not None:
        if status not in ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "UNKNOWN"):
            raise ApiError(422, ErrorCode.INVALID_OPERATION, f"unknown status {status!r}")
        stmt = stmt.where(DeploymentOperation.status == status)
    rows = db.scalars(stmt.limit(limit)).all()
    items = [svc._op_out(r) for r in rows]
    return OperationListResponse(operations=items, count=len(items))


@router.get("/operations/{operation_id}/events", response_model=OperationEventsResponse)
def read_operation_events(operation_id: str, db: Session = Depends(get_db)) -> OperationEventsResponse:
    """Append-only event log for one operation (id ASC = causal order)."""
    svc.get_operation(db, operation_id)  # 404 when unknown
    rows = db.scalars(
        select(OperationEvent)
        .where(OperationEvent.operation_id == operation_id)
        .order_by(OperationEvent.id.asc())
    ).all()
    return OperationEventsResponse(
        operation_id=operation_id,
        events=[
            OperationEventOut(id=e.id, at=e.at, event=e.event, detail=e.detail)
            for e in rows
        ],
    )
