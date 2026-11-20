"""RC2 F04: Docker disablement must block every mutation type at dispatch.

Submission-time gating already exists (ADMIN + host.docker_enabled). These
tests pin the dispatch-time gate: an operation queued while Docker was enabled
must NOT be delivered after an operator disables Docker, and it must remain
queued (not lost) for when Docker is re-enabled.
"""

from backend.tests.conftest import auth_headers
from backend.tests.test_deployments import deploy
from backend.tests.test_docker_authz import _login_admin, _patch_docker


def _poll(client, host_id, token):
    return client.post("/api/v1/agents/commands/poll", headers=auth_headers(host_id, token)).json()["commands"]


def _report(client, host_id, token, op_id, state="RUNNING"):
    resp = client.post(
        f"/api/v1/agents/commands/{op_id}/result",
        json={
            "status": "SUCCEEDED",
            "result": {"container_state": state, "http_ok": state == "RUNNING"},
        },
        headers=auth_headers(host_id, token),
    )
    assert resp.status_code == 200, resp.text


def _queue_lifecycle(client, admin, dep_id, action):
    resp = client.post(
        f"/api/v1/applications/{dep_id}/{action}",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert resp.status_code == 202, resp.text
    return resp.json()["operation_id"]


def test_docker_disable_blocks_every_queued_mutation(client, online_host):
    host_id, token = online_host
    admin = _login_admin(client)

    first = deploy(client, host_id).json()
    dep_id = first["deployment_id"]
    claimed = _poll(client, host_id, token)
    assert len(claimed) == 1
    _report(client, host_id, token, claimed[0]["id"])

    for action, expected_type, resulting_state in (
        ("stop", "STOP", "EXITED"),
        ("start", "START", "RUNNING"),
        ("restart", "RESTART", "RUNNING"),
    ):
        op_id = _queue_lifecycle(client, admin, dep_id, action)

        # Disable after the operation is already queued.
        _patch_docker(client, admin, host_id, False)
        assert _poll(client, host_id, token) == [], f"{action} leaked past disablement"

        # Re-enable: the operation is still there (queued, not lost).
        _patch_docker(client, admin, host_id, True)
        claimed = _poll(client, host_id, token)
        assert [c["id"] for c in claimed] == [op_id], action
        assert claimed[0]["op_type"] == expected_type
        _report(client, host_id, token, op_id, resulting_state)

    # DEPLOY is also a Docker mutation and must be blocked at dispatch.
    resp = client.post(
        "/api/v1/applications/deploy",
        json={"host_id": host_id, "template_key": "nginx-demo"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert resp.status_code == 202, resp.text
    deploy_op = resp.json()["operation_id"]

    _patch_docker(client, admin, host_id, False)
    assert _poll(client, host_id, token) == [], "DEPLOY leaked past disablement"
    _patch_docker(client, admin, host_id, True)
    assert [c["id"] for c in _poll(client, host_id, token)] == [deploy_op]


def test_new_submission_is_rejected_while_disabled(client, online_host):
    host_id, _ = online_host
    admin = _login_admin(client)
    dep_id = deploy(client, host_id).json()["deployment_id"]
    _patch_docker(client, admin, host_id, False)

    resp = client.post(
        f"/api/v1/applications/{dep_id}/stop",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "DOCKER_NOT_AUTHORIZED"
