"""Automatic setup must be opt-in and ADMIN-only."""

from backend.app.api.operators import require_operator
from backend.app.main import app


def test_targets_require_authentication(client):
    assert client.get("/api/v1/provisioning/targets").status_code == 401


def test_unknown_target_never_connects(client, monkeypatch):
    from backend.app.api import provisioning
    from types import SimpleNamespace

    app.dependency_overrides[provisioning.admin] = lambda: SimpleNamespace(id="admin")
    monkeypatch.delenv("NIMBUSOPS_SSH_TARGETS_FILE", raising=False)
    try:
        assert client.get("/api/v1/provisioning/targets").json() == {"targets": []}
        response = client.post(
            "/api/v1/provisioning/preflight", json={"target_id": "arbitrary"}
        )
        assert response.status_code == 404
        response = client.post(
            "/api/v1/provisioning/preflight",
            json={
                "target_id": "arbitrary",
                "command": "whoami",
                "password": "not-accepted",
            },
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_confirm_and_jobs_require_authentication(client):
    assert (
        client.post(
            "/api/v1/provisioning/confirm",
            json={
                "target_id": "test",
                "validation_id": "test",
                "approval_hash": "a" * 64,
                "confirmed": True,
            },
        ).status_code
        == 401
    )
    assert client.get("/api/v1/provisioning/jobs/unknown").status_code == 401


def test_viewer_cannot_inspect_confirm_or_retry(client, db_session):
    from backend.tests.test_operator_auth import _seed_operator, _login

    _seed_operator(db_session, role="VIEWER")
    token = _login(client).json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert (
        client.get("/api/v1/provisioning/targets", headers=headers).status_code == 403
    )
    assert (
        client.post(
            "/api/v1/provisioning/preflight",
            headers=headers,
            json={"target_id": "test"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/provisioning/jobs/unknown/retry", headers=headers
        ).status_code
        == 403
    )
