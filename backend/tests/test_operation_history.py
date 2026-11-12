"""FR-08: operation history API — list with filters + per-op event log.

Pins:
- GET /operations?host_id=&status=&limit= filters and bounds,
- events are append-only ordered (id ASC) and carry no token material,
- unknown ids → 404 structured errors.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict[str, str]:
    """One host + one deployment + three ops in mixed states."""
    from backend.app.core.db import session_scope
    from backend.app.models import (
        DeploymentOperation,
        DeploymentTemplate,
        Host,
        ManagedDeployment,
        OperationEvent,
    )

    with session_scope() as db:
        if db.get(DeploymentTemplate, "nginx") is None:
            db.add(DeploymentTemplate(key="nginx", name="Nginx demo",
                                      image="nginx:1.27-alpine",
                                      container_port=80, host_port=18080))
        db.add(Host(id="h-hist-1", hostname="history-host.example.test",
                    agent_token_hash="0" * 64, enrollment_status="ENROLLED",
                    docker_enabled=True, environment="PRIVATE"))
        db.flush()
        db.add(ManagedDeployment(id="dep-hist-1", host_id="h-hist-1",
                                 template_key="nginx",
                                 container_name="nimbusops-nginx-hist"))
        db.flush()
        ops: dict[str, str] = {}
        for oid, status, otype in [
            ("op-hist-a", "SUCCEEDED", "DEPLOY"),
            ("op-hist-b", "FAILED", "START"),
            ("op-hist-c", "QUEUED", "RESTART"),
        ]:
            db.add(DeploymentOperation(id=oid, deployment_id="dep-hist-1",
                                       host_id="h-hist-1", op_type=otype,
                                       status=status))
            ops[oid] = status
        db.add(OperationEvent(operation_id="op-hist-a", event="CREATED"))
        db.add(OperationEvent(operation_id="op-hist-a", event="RESULT",
                              detail="status=SUCCEEDED"))
        db.add(OperationEvent(operation_id="op-hist-b", event="CREATED"))
    return {"host": "h-hist-1", "dep": "dep-hist-1", "ops": ops}


def test_list_operations_all(client):
    _seed(client)
    r = client.get("/api/v1/operations")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 3
    ids = [o["id"] for o in body["operations"]]
    assert ids == ["op-hist-a", "op-hist-b", "op-hist-c"]  # newest last (created ASC? pin stable order)


def test_list_operations_filter_status(client):
    _seed(client)
    body = client.get("/api/v1/operations", params={"status": "FAILED"}).json()
    assert body["count"] == 1
    assert body["operations"][0]["id"] == "op-hist-b"


def test_list_operations_filter_host(client):
    _seed(client)
    body = client.get("/api/v1/operations", params={"host_id": "h-hist-1"}).json()
    assert body["count"] == 3
    body2 = client.get("/api/v1/operations", params={"host_id": "h-other"}).json()
    assert body2["count"] == 0


def test_list_operations_limit_and_order(client):
    _seed(client)
    body = client.get("/api/v1/operations", params={"limit": 2}).json()
    assert body["count"] == 2
    # Bounded result; deterministic ordering required.
    assert [o["id"] for o in body["operations"]] == ["op-hist-a", "op-hist-b"]


def test_list_operations_limit_validated(client):
    _seed(client)
    assert client.get("/api/v1/operations", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/operations", params={"limit": 501}).status_code == 422


def test_operation_events_ordered_and_sanitized(client):
    _seed(client)
    r = client.get("/api/v1/operations/op-hist-a/events")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [e["event"] for e in body["events"]] == ["CREATED", "RESULT"]
    # Sanitization pin: no token-looking material ever appears.
    blob = str(body)
    assert "agent_token" not in blob
    assert "session_token" not in blob


def test_operation_events_unknown_op_404(client):
    _seed(client)
    r = client.get("/api/v1/operations/op-does-not-exist/events")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "OPERATION_NOT_FOUND"


def test_operation_detail_unknown_404(client):
    r = client.get("/api/v1/operations/op-does-not-exist")
    assert r.status_code == 404
