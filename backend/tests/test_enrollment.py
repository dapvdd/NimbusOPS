"""Health endpoint and enrollment authorization tests."""

from backend.tests.conftest import auth_headers


def test_health_ok(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "nimbusops-control-server"
    assert body["database"] == "ok"


def test_enroll_without_token_configured_fails(client, monkeypatch):
    from backend.app.core.config import get_settings

    get_settings().enrollment_token = ""
    resp = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "h", "enrollment_token": "whatever"},
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "ENROLLMENT_DISABLED"
    get_settings().enrollment_token = "test-enroll-token"


def test_enroll_with_wrong_token_rejected(client, enroll_token):
    resp = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "host-x", "enrollment_token": "wrong-token"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_enroll_success_returns_token_once(client, enroll_token):
    resp = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "host-ok", "enrollment_token": enroll_token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["host_id"]
    assert len(body["agent_token"]) >= 32


def test_legacy_duplicate_hostname_cannot_replace_credential(client, enroll_token):
    """RC2 F08: the shared token is not a credential-replacement mechanism.

    Re-enrollment must go through an operator-issued bootstrap token; a second
    legacy enroll for the same hostname is refused and the original agent
    credential stays valid.
    """
    r1 = client.post("/api/v1/agents/enroll", json={"hostname": "dup", "enrollment_token": enroll_token})
    assert r1.status_code == 200
    r1_body = r1.json()

    r2 = client.post("/api/v1/agents/enroll", json={"hostname": "dup", "enrollment_token": enroll_token})
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "HOSTNAME_TAKEN"

    # The original token must still authenticate (no silent rotation).
    resp = client.post(
        "/api/v1/agents/heartbeat",
        headers=auth_headers(r1_body["host_id"], r1_body["agent_token"]),
        json={},
    )
    assert resp.status_code == 200
