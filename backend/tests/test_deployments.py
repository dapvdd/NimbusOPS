"""Phase 2 backend tests: templates, deployments, operations, command delivery.

All Docker-touching behavior is at the agent boundary; these tests cover the
control plane only (contracts, duplicate protection, auth, persistence).
"""

import pytest

from backend.tests.conftest import auth_headers

# `online_host` fixture now lives in conftest.py (shared with test_recovery.py).


def deploy(client, host_id, template_key="nginx-demo"):
    """Deploy helper.

    Phase 3B: mutations require an operator session and docker_enabled=true.
    The helper logs in (get-or-create admin), enables Docker, and sends the
    authenticated request so Phase 2 tests keep exercising deploy semantics.
    """
    from backend.tests.test_docker_authz import _login_admin, _patch_docker

    admin = _login_admin(client)
    _patch_docker(client, admin, host_id, True)
    return client.post(
        "/api/v1/applications/deploy",
        json={"host_id": host_id, "template_key": template_key},
        headers={"Authorization": f"Bearer {admin}"},
    )


# ----------------------------------------------------------------- templates


def test_list_templates_lists_approved_nginx(client):
    resp = client.get("/api/v1/templates")
    assert resp.status_code == 200
    body = resp.json()
    keys = [t["key"] for t in body["templates"]]
    assert "nginx-demo" in keys
    tmpl = next(t for t in body["templates"] if t["key"] == "nginx-demo")
    assert tmpl["image"].startswith("nginx:")
    assert tmpl["is_approved"] is True


def test_nginx_demo_template_uses_stageb_host_port(client):
    """Stage B: DavidLab hosts SPECTRA on 8080; the demo must publish 18080."""
    resp = client.get("/api/v1/templates")
    assert resp.status_code == 200
    tmpl = next(t for t in resp.json()["templates"] if t["key"] == "nginx-demo")
    assert tmpl["host_port"] == 18080


# ------------------------------------------------------------ deploy happy path


def test_deploy_returns_operation_and_persists(client, online_host):
    host_id, _ = online_host
    resp = deploy(client, host_id)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "QUEUED"
    assert body["operation_id"]
    assert body["deployment_id"]
    assert body["template_key"] == "nginx-demo"
    # Durable: readable back from the operations endpoint.
    op = client.get(f"/api/v1/operations/{body['operation_id']}")
    assert op.status_code == 200
    assert op.json()["status"] == "QUEUED"


def test_deploy_unknown_host_404(client):
    resp = deploy(client, "no-such-host-id")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "HOST_NOT_FOUND"


def test_deploy_unknown_template_422(client, online_host):
    host_id, _ = online_host
    resp = deploy(client, host_id, template_key="not-a-template")
    assert resp.status_code == 422


def test_deploy_to_offline_host_still_allowed(client, enroll_token):
    """Offline hosts may receive queued ops; agent picks them up on reconnect."""
    resp = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "offline-host", "enrollment_token": enroll_token},
    )
    host_id = resp.json()["host_id"]
    resp = deploy(client, host_id)
    assert resp.status_code == 202


# --------------------------------------------------------- duplicate protection


def test_duplicate_deploy_while_queued_returns_same_operation(client, online_host):
    host_id, _ = online_host
    first = deploy(client, host_id)
    assert first.status_code == 202
    second = deploy(client, host_id)
    assert second.status_code == 202
    # Same deployment + operation: no uncontrolled duplicates.
    assert second.json()["operation_id"] == first.json()["operation_id"]
    assert second.json()["deployment_id"] == first.json()["deployment_id"]


def test_redeploy_after_terminal_operation_creates_new_operation(client, online_host):
    host_id, token = online_host
    first = deploy(client, host_id)
    op_id = first.json()["operation_id"]
    dep_id = first.json()["deployment_id"]
    # Agent completes the first operation.
    poll = client.post("/api/v1/agents/commands/poll", headers=auth_headers(host_id, token))
    cmd = next(c for c in poll.json()["commands"] if c["id"] == op_id)
    client.post(
        f"/api/v1/agents/commands/{op_id}/result",
        json={"status": "SUCCEEDED", "result": {"container_id": "abc123"}},
        headers=auth_headers(host_id, token),
    )
    # Second deploy now creates a NEW operation for the SAME deployment.
    second = deploy(client, host_id)
    assert second.status_code == 202
    assert second.json()["deployment_id"] == dep_id
    assert second.json()["operation_id"] != op_id


# ------------------------------------------------------------- agent command API


def test_command_poll_requires_agent_auth(client, online_host):
    host_id, token = online_host
    deploy(client, host_id)
    resp = client.post("/api/v1/agents/commands/poll")
    assert resp.status_code == 401
    resp = client.post("/api/v1/agents/commands/poll", headers=auth_headers(host_id, "wrong-token"))
    assert resp.status_code == 401


def test_command_poll_claims_once_and_scopes_to_host(client, online_host):
    host_id, token = online_host
    op_id = deploy(client, host_id).json()["operation_id"]
    r1 = client.post("/api/v1/agents/commands/poll", headers=auth_headers(host_id, token))
    cmds = r1.json()["commands"]
    assert len(cmds) == 1
    assert cmds[0]["id"] == op_id
    assert cmds[0]["op_type"] == "DEPLOY"
    assert cmds[0]["template"]["key"] == "nginx-demo"
    # Claimed: second poll does NOT re-deliver.
    r2 = client.post("/api/v1/agents/commands/poll", headers=auth_headers(host_id, token))
    assert r2.json()["commands"] == []


def test_other_host_cannot_poll_foreign_commands(client, enroll_token):
    r1 = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "host-a", "enrollment_token": enroll_token},
    )
    r2 = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "host-b", "enrollment_token": enroll_token},
    )
    a_id, a_tok = r1.json()["host_id"], r1.json()["agent_token"]
    b_id, b_tok = r2.json()["host_id"], r2.json()["agent_token"]
    deploy(client, a_id)
    # Host B polls: must not see host A's commands.
    rb = client.post("/api/v1/agents/commands/poll", headers=auth_headers(b_id, b_tok))
    assert rb.json()["commands"] == []
    ra = client.post("/api/v1/agents/commands/poll", headers=auth_headers(a_id, a_tok))
    assert len(ra.json()["commands"]) == 1


def test_result_validation_rejects_bad_status(client, online_host):
    host_id, token = online_host
    op_id = deploy(client, host_id).json()["operation_id"]
    client.post("/api/v1/agents/commands/poll", headers=auth_headers(host_id, token))
    resp = client.post(
        f"/api/v1/agents/commands/{op_id}/result",
        json={"status": "TOTALLY_BOGUS"},
        headers=auth_headers(host_id, token),
    )
    assert resp.status_code == 422


def test_result_unknown_command_404(client, online_host):
    host_id, token = online_host
    resp = client.post(
        "/api/v1/agents/commands/does-not-exist/result",
        json={"status": "SUCCEEDED", "result": {}},
        headers=auth_headers(host_id, token),
    )
    assert resp.status_code == 404


def test_result_wrong_host_403(client, enroll_token):
    r1 = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "host-a", "enrollment_token": enroll_token},
    )
    r2 = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "host-b", "enrollment_token": enroll_token},
    )
    a_id, a_tok = r1.json()["host_id"], r1.json()["agent_token"]
    b_id, b_tok = r2.json()["host_id"], r2.json()["agent_token"]
    op_id = deploy(client, a_id).json()["operation_id"]
    client.post("/api/v1/agents/commands/poll", headers=auth_headers(a_id, a_tok))
    resp = client.post(
        f"/api/v1/agents/commands/{op_id}/result",
        json={"status": "SUCCEEDED", "result": {}},
        headers=auth_headers(b_id, b_tok),
    )
    assert resp.status_code == 403


# ------------------------------------------------------- lifecycle: start / stop


def test_stop_then_start_lifecycle(client, online_host):
    host_id, token = online_host
    dep_id = deploy(client, host_id).json()["deployment_id"]
    op_id = deploy(client, host_id).json()["operation_id"]  # same op (dedup)
    # Simulate agent having deployed: poll, then report success with evidence.
    client.post("/api/v1/agents/commands/poll", headers=auth_headers(host_id, token))
    client.post(
        f"/api/v1/agents/commands/{op_id}/result",
        json={"status": "SUCCEEDED", "result": {"container_state": "RUNNING", "http_ok": True}},
        headers=auth_headers(host_id, token),
    )
    # Stop the deployment (operator auth required in Phase 3B).
    from backend.tests.test_docker_authz import _login_admin

    admin = _login_admin(client)
    stop = client.post(f"/api/v1/applications/{dep_id}/stop", headers={"Authorization": f"Bearer {admin}"})
    assert stop.status_code == 202, stop.text
    stop_body = stop.json()
    assert stop_body["status"] == "QUEUED"
    assert stop_body["deployment_id"] == dep_id
    assert stop_body["template_key"] == "nginx-demo"


def test_stop_requires_existing_deployment(client):
    """Unauthenticated first (operator gate), then unknown deployment 404."""
    resp = client.post("/api/v1/applications/no-such-deployment/stop")
    assert resp.status_code == 401
    from backend.tests.test_docker_authz import _login_admin

    admin = _login_admin(client)
    resp = client.post(
        "/api/v1/applications/no-such-deployment/stop",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert resp.status_code == 404


def test_lifecycle_commands_carry_template_payload(client, online_host):
    """Stage B regression: START/STOP commands must include the template
    (container_name etc.) or the agent cannot name the container and the
    real run failed with UNAPPROVED_OPERATION ("container name '' outside
    managed prefix"). Mirrors the DEPLOY template attachment."""
    host_id, token = online_host
    dep_id = deploy(client, host_id).json()["deployment_id"]
    # Simulate successful deploy so lifecycle ops are queueable.
    op_id = client.post("/api/v1/agents/commands/poll", headers=auth_headers(host_id, token)).json()["commands"][0]["id"]
    client.post(
        f"/api/v1/agents/commands/{op_id}/result",
        json={"status": "SUCCEEDED", "result": {"container_state": "RUNNING", "http_ok": True}},
        headers=auth_headers(host_id, token),
    )
    for lifecycle in ("stop", "start"):
        from backend.tests.test_docker_authz import _login_admin

        admin = _login_admin(client)
        op = client.post(
            f"/api/v1/applications/{dep_id}/{lifecycle}",
            headers={"Authorization": f"Bearer {admin}"},
        ).json()
        poll = client.post("/api/v1/agents/commands/poll", headers=auth_headers(host_id, token)).json()
        cmd = next(c for c in poll["commands"] if c["id"] == op["operation_id"])
        assert cmd["template"] is not None, f"{lifecycle} command must carry template"
        assert cmd["template"]["container_name"] == "nimbusops-nginx-demo-" + host_id[:8]
        assert cmd["template"]["key"] == "nginx-demo"
        # Complete it so the next lifecycle op is queueable.
        client.post(
            f"/api/v1/agents/commands/{cmd['id']}/result",
            json={"status": "SUCCEEDED", "result": {"container_state": "EXITED", "http_ok": None}},
            headers=auth_headers(host_id, token),
        )


def test_container_state_endpoint(client, online_host):
    host_id, _ = online_host
    dep_id = deploy(client, host_id).json()["deployment_id"]
    resp = client.get(f"/api/v1/applications/{dep_id}/container-state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["deployment_id"] == dep_id
    # No agent has reported yet: honest unknown, not fabricated.
    assert body["container_state"] in ("UNKNOWN", None, "NOT_REPORTED")
    assert body["http_ok"] is None or body["http_ok"] is False


# ------------------------------------------------------------ operation reading


def test_operation_states_transitions_visible(client, online_host):
    host_id, token = online_host
    op_id = deploy(client, host_id).json()["operation_id"]
    client.post("/api/v1/agents/commands/poll", headers=auth_headers(host_id, token))
    op = client.get(f"/api/v1/operations/{op_id}").json()
    assert op["status"] == "RUNNING"
    client.post(
        f"/api/v1/agents/commands/{op_id}/result",
        json={"status": "FAILED", "error_code": "DOCKER_FAILURE", "error_message": "pull failed"},
        headers=auth_headers(host_id, token),
    )
    op = client.get(f"/api/v1/operations/{op_id}").json()
    assert op["status"] == "FAILED"
    assert op["error_code"] == "DOCKER_FAILURE"
    assert op["error_message"] == "pull failed"
    assert op["updated_at"] >= op["created_at"]


def test_unauthed_mutation_rejected(client, online_host):
    """REWRITTEN Phase 2 pin (was: unauthenticated mutation accepted 202).

    Phase 3B AC-01: application mutations require an operator session —
    401 without, 202 with (gerbang keamanan, bukan pelemahan).
    """
    from backend.tests.test_docker_authz import _login_admin

    admin = _login_admin(client)
    host_id, _ = online_host
    assert client.patch(
        f"/api/v1/hosts/{host_id}",
        headers={"Authorization": f"Bearer {admin}"},
        json={"docker_enabled": True},
    ).status_code == 200

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
