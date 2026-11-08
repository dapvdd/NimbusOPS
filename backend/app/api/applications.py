"""Applications API (browser-facing): templates, deploy, lifecycle, state.

Phase 2 trusted-local model: mutating application endpoints are
browser-initiated and documented as unauthenticated in docs/SECURITY.md
(restriction: trusted local development environments only).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import DeploymentTemplate
from ..schemas import (
    ContainerStateResponse,
    DeployRequest,
    DeployResponse,
    ManagedAppListResponse,
    OperationOut,
    TemplateListResponse,
)
from ..services import deployments as svc

router = APIRouter(prefix="/api/v1")


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
def deploy(req: DeployRequest, db: Session = Depends(get_db)) -> DeployResponse:
    dep, op, dedup = svc.create_deployment(db, req)
    return _op_response(db, dep, op, dedup)


@router.post("/applications/{deployment_id}/start", response_model=DeployResponse, status_code=202)
def start_app(deployment_id: str, db: Session = Depends(get_db)) -> DeployResponse:
    dep, op, dedup = svc.create_lifecycle_operation(db, deployment_id, "START")
    return _op_response(db, dep, op, dedup)


@router.post("/applications/{deployment_id}/stop", response_model=DeployResponse, status_code=202)
def stop_app(deployment_id: str, db: Session = Depends(get_db)) -> DeployResponse:
    dep, op, dedup = svc.create_lifecycle_operation(db, deployment_id, "STOP")
    return _op_response(db, dep, op, dedup)


@router.get("/applications/{deployment_id}/container-state", response_model=ContainerStateResponse)
def container_state(deployment_id: str, db: Session = Depends(get_db)) -> ContainerStateResponse:
    return ContainerStateResponse(**svc.get_container_state(db, deployment_id))


@router.get("/operations/{operation_id}", response_model=OperationOut)
def read_operation(operation_id: str, db: Session = Depends(get_db)) -> OperationOut:
    return svc._op_out(svc.get_operation(db, operation_id))
