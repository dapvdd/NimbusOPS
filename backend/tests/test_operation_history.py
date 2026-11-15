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
    assert body["total"] == 3
    ids = [o["id"] for o in body["operations"]]
    # RC2 F10: newest first. A bounded window that starts at the oldest row
    # hides every recent operation from the operator.
    assert ids == ["op-hist-c", "op-hist-b", "op-hist-a"]


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
    assert body["total"] == 3
    # Newest-first bounded window.
    assert [o["id"] for o in body["operations"]] == ["op-hist-c", "op-hist-b"]


def test_list_operations_offset_reaches_older_rows(client):
    """RC2 F10: offset navigation must reach rows beyond the first window."""
    _seed(client)
    first = client.get("/api/v1/operations", params={"limit": 2}).json()
    second = client.get("/api/v1/operations", params={"limit": 2, "offset": 2}).json()
    assert first["total"] == second["total"] == 3
    assert [o["id"] for o in first["operations"]] == ["op-hist-c", "op-hist-b"]
    assert [o["id"] for o in second["operations"]] == ["op-hist-a"]
    assert client.get("/api/v1/operations", params={"offset": -1}).status_code == 422


def test_list_operations_status_filter_is_server_side(client):
    """A status filter must narrow the set before the window is taken."""
    _seed(client)
    body = client.get("/api/v1/operations", params={"status": "SUCCEEDED", "limit": 1}).json()
    assert body["total"] == 1
    assert [o["id"] for o in body["operations"]] == ["op-hist-a"]


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
