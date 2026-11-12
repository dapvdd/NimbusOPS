"""Phase 5: RESTART operation end-to-end (queue → claim → result).

Restart is a destructive-ish lifecycle op: ADMIN-only dispatch target,
allowlisted op_type, docker-disabled hosts get 403 before queueing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _seed_operator_and_host(client: TestClient, *, docker_enabled: bool = True) -> tuple[str, str]:
    """Returns (operator_session_token, host_id) with a seeded deployment."""
    from backend.app.core.config import get_settings
    from backend.app.core.db import session_scope
    from backend.app.core.security import hash_operator_password
    from backend.app.models import Host, Operator

    with session_scope() as db:
        db.add(Operator(id="op-rst", username="rst_admin",
                        password_hash=hash_operator_password("pw-rst"),
                        role="ADMIN"))
        db.add(Host(id="h-rst-1", hostname="restart-host.example.test",
                    agent_token_hash="0" * 64, enrollment_status="ENROLLED",
                    docker_enabled=docker_enabled, environment="PRIVATE"))
    r = client.post("/api/v1/operators/login",
                    json={"username": "rst_admin", "password": "pw-rst"})
    assert r.status_code == 200, r.text
    return r.json()["session_token"], "h-rst-1"


def _seed_deployment(client: TestClient) -> str:
    """Insert a managed deployment directly (no dispatch)."""
    from backend.app.core.db import session_scope
    from backend.app.models import DeploymentTemplate, ManagedDeployment

    with session_scope() as db:
        if db.get(DeploymentTemplate, "nginx") is None:
            db.add(DeploymentTemplate(key="nginx", name="Nginx demo",
                                      image="nginx:1.27-alpine",
                                      container_port=80, host_port=18080))
        db.add(ManagedDeployment(
            id="dep-rst-1", host_id="h-rst-1", template_key="nginx",
            container_name="nimbusops-nginx-rst",
        ))
    return "dep-rst-1"


def test_restart_op_queued_and_returned_202(client):
    token, _ = _seed_operator_and_host(client)
    dep_id = _seed_deployment(client)
    r = client.post(f"/api/v1/applications/{dep_id}/restart",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["op_type"] == "RESTART"
    assert body["status"] == "QUEUED"


def test_restart_docker_disabled_host_403(client):
    token, _ = _seed_operator_and_host(client, docker_enabled=False)
    dep_id = _seed_deployment(client)
    r = client.post(f"/api/v1/applications/{dep_id}/restart",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "DOCKER_NOT_AUTHORIZED"


def test_restart_requires_admin_role(client):
    from backend.app.core.db import session_scope
    from backend.app.core.security import hash_operator_password
    from backend.app.models import Operator

    with session_scope() as db:
        db.add(Operator(id="op-view", username="rst_viewer",
                        password_hash=hash_operator_password("pw-view"),
                        role="VIEWER"))
    _seed_operator_and_host(client)
    dep_id = _seed_deployment(client)
    r = client.post("/api/v1/operators/login",
                    json={"username": "rst_viewer", "password": "pw-view"})
    vtok = r.json()["session_token"]
    r = client.post(f"/api/v1/applications/{dep_id}/restart",
                    headers={"Authorization": f"Bearer {vtok}"})
    assert r.status_code == 403


def test_restart_op_claimed_by_agent_poll(client):
    """Poll flow: queued RESTART is claimed with template payload."""
    token, host_id = _seed_operator_and_host(client)
    dep_id = _seed_deployment(client)
    r = client.post(f"/api/v1/applications/{dep_id}/restart",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 202, r.text
    op_id = r.json()["operation_id"]

    # Agent polls (docker_enabled True).
    from backend.app.core.db import session_scope
    from backend.app.services import deployments as dep_service

    with session_scope() as db:
        commands = dep_service.poll_commands(db, host_id, docker_enabled=True)
    assert any(c.id == op_id and c.op_type == "RESTART" for c in commands), commands
