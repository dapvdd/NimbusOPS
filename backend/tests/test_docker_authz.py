"""Task 6: Docker default-off + server-side sim- rejection.

Covers contract §5.2/§5.3/§6:
- deploy/start/stop on a docker_enabled=false host → 403 DOCKER_NOT_AUTHORIZED,
  no op row created
- after PATCH docker_enabled=true → 202 (operator auth required for the PATCH)
- heartbeat response carries docker_enabled
- poll on a disabled host yields no DEPLOY ops (they stay QUEUED)
- X-Host-Id sim-* → 400 SIMULATED_HOST_REJECTED on agent endpoints
- rewrite of the Phase 2 pin: mutations require operator auth (401 without,
  202 with)
"""

from backend.tests.conftest import auth_headers


def _login_admin(client) -> str:
    from backend.tests.test_operator_auth import _seed_operator

    _seed_operator(_db(), username="admin", password="secret-pw")
    resp = client.post("/api/v1/operators/login", json={"username": "admin", "password": "secret-pw"})
    assert resp.status_code == 200, resp.text
    return resp.json()["session_token"]


def _db():
    from backend.app.core.db import SessionLocal

    return SessionLocal()


def _patch_docker(client, admin, host_id, enabled: bool):
    return client.patch(
        f"/api/v1/hosts/{host_id}",
        headers={"Authorization": f"Bearer {admin}"},
        json={"docker_enabled": enabled},
    )


def test_deploy_to_docker_disabled_host_403(client, online_host):
    admin = _login_admin(client)
    host_id, _ = online_host  # docker_enabled defaults to False
    resp = client.post(
        "/api/v1/applications/deploy",
        headers={"Authorization": f"Bearer {admin}"},
        json={"host_id": host_id, "template_key": "nginx-demo"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "DOCKER_NOT_AUTHORIZED"
    # No op row created.
    from sqlalchemy import select

    from backend.app.models import DeploymentOperation

    db = _db()
    try:
        ops = db.scalars(select(DeploymentOperation).where(DeploymentOperation.host_id == host_id)).all()
        assert ops == []
    finally:
        db.close()


def test_deploy_after_docker_enabled_202(client, online_host):
    admin = _login_admin(client)
    host_id, _ = online_host
    assert _patch_docker(client, admin, host_id, True).status_code == 200
    resp = client.post(
        "/api/v1/applications/deploy",
        headers={"Authorization": f"Bearer {admin}"},
        json={"host_id": host_id, "template_key": "nginx-demo"},
    )
    assert resp.status_code == 202


def test_start_stop_require_docker_enabled(client, online_host):
    admin = _login_admin(client)
    host_id, _ = online_host
    assert _patch_docker(client, admin, host_id, True).status_code == 200
    dep = client.post(
        "/api/v1/applications/deploy",
        headers={"Authorization": f"Bearer {admin}"},
        json={"host_id": host_id, "template_key": "nginx-demo"},
    ).json()
    dep_id = dep["deployment_id"]
    # Disable Docker again → start/stop blocked.
    assert _patch_docker(client, admin, host_id, False).status_code == 200
    for action in ("start", "stop"):
        resp = client.post(
            f"/api/v1/applications/{dep_id}/{action}",
            headers={"Authorization": f"Bearer {admin}"},
        )
        assert resp.status_code == 403, (action, resp.text)
        assert resp.json()["error"]["code"] == "DOCKER_NOT_AUTHORIZED"


def test_heartbeat_carries_docker_enabled(client, online_host):
    admin = _login_admin(client)
    host_id, token = online_host
    resp = client.post(
        "/api/v1/agents/heartbeat",
        headers=auth_headers(host_id, token),
        json={},
    )
    assert resp.status_code == 200
    assert resp.json()["docker_enabled"] is False


def test_poll_disabled_host_no_deploy_ops(client, online_host):
    admin = _login_admin(client)
    host_id, token = online_host
    assert _patch_docker(client, admin, host_id, True).status_code == 200
    dep = client.post(
        "/api/v1/applications/deploy",
        headers={"Authorization": f"Bearer {admin}"},
        json={"host_id": host_id, "template_key": "nginx-demo"},
    ).json()
    assert dep["status"] == "QUEUED"
    # Disable Docker: the queued DEPLOY op is not deliverable.
    assert _patch_docker(client, admin, host_id, False).status_code == 200
    resp = client.post("/api/v1/agents/commands/poll", headers=auth_headers(host_id, token), json={})
    assert resp.status_code == 200
    assert resp.json()["commands"] == []
    # Re-enable → deliverable again.
    assert _patch_docker(client, admin, host_id, True).status_code == 200
    resp = client.post("/api/v1/agents/commands/poll", headers=auth_headers(host_id, token), json={})
    assert len(resp.json()["commands"]) == 1


# ------------------------------------------------------- server-side sim guard


def test_agent_endpoints_reject_sim_host_id(client):
    """Server-side guard: sim-* host ids never reach service logic (400)."""
    h = {"X-Host-Id": "sim-1234", "Authorization": "Bearer whatever"}
    hb = client.post("/api/v1/agents/heartbeat", headers=h, json={})
    assert hb.status_code == 400
    assert hb.json()["error"]["code"] == "SIMULATED_HOST_REJECTED"
    poll = client.post("/api/v1/agents/commands/poll", headers=h, json={})
    assert poll.status_code == 400
    assert poll.json()["error"]["code"] == "SIMULATED_HOST_REJECTED"
    result = client.post("/api/v1/agents/commands/whatever/result", headers=h, json={"status": "SUCCEEDED"})
    assert result.status_code == 400
    assert result.json()["error"]["code"] == "SIMULATED_HOST_REJECTED"


def test_enroll_rejects_sim_hostname(client):
    resp = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "sim-ghost", "enrollment_token": "test-enroll-token"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SIMULATED_HOST_REJECTED"


# -------------------------------------------------- rewritten Phase 2 pin (AC-01)


def test_unauthed_mutation_rejected(client, online_host):
    """REWRITTEN Phase 2 pin (was: unauthenticated mutation accepted 202).

    Phase 3B AC-01: application mutations require an operator session —
    401 without, 202 with.
    """
    admin = _login_admin(client)
    host_id, _ = online_host
    assert _patch_docker(client, admin, host_id, True).status_code == 200

    no_auth = client.post(
        "/api/v1/applications/deploy",
        json={"host_id": host_id, "template_key": "nginx-demo"},
    )
    assert no_auth.status_code == 401
    assert no_auth.json()["error"]["code"] == "OPERATOR_AUTH_REQUIRED"

    ok = client.post(
        "/api/v1/applications/deploy",
        headers={"Authorization": f"Bearer {admin}"},
        json={"host_id": host_id, "template_key": "nginx-demo"},
    )
    assert ok.status_code == 202


def test_viewer_can_read_but_not_mutate(client, online_host):
    from backend.tests.test_operator_auth import _seed_operator

    _seed_operator(_db(), username="viewer", role="VIEWER")
    viewer = client.post("/api/v1/operators/login", json={"username": "viewer", "password": "secret-pw"}).json()["session_token"]
    host_id, _ = online_host
    assert _patch_docker(client, viewer, host_id, True).status_code == 403
    resp = client.post(
        "/api/v1/applications/deploy",
        headers={"Authorization": f"Bearer {viewer}"},
        json={"host_id": host_id, "template_key": "nginx-demo"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "OPERATOR_FORBIDDEN"
