"""RC2 F01/F08: canonical enrollment contract and legacy-path hardening.

These tests pin the RC2 contract:

- Exactly one enrollment credential may be presented. Supplying both the
  legacy shared token and a bootstrap token is ambiguous and rejected.
- ``NIMBUSOPS_ENROLLMENT_MODE=bootstrap`` is the secure deployment profile:
  the legacy shared-token path is disabled entirely.
- A shared enrollment secret may never silently replace an existing host's
  credential by hostname. Re-enrollment requires an operator-issued,
  hostname-scoped, single-use bootstrap token.
"""

from backend.tests.conftest import auth_headers
from backend.tests.test_bootstrap_enrollment import _admin, _issue


def _legacy_enroll(client, hostname: str, token: str):
    return client.post(
        "/api/v1/agents/enroll",
        json={"hostname": hostname, "enrollment_token": token},
    )


def _bootstrap_enroll(client, hostname: str, token: str):
    return client.post(
        "/api/v1/agents/enroll",
        json={"hostname": hostname, "bootstrap_token": token},
    )


def test_conflicting_enrollment_credentials_rejected(client, db_session, enroll_token):
    admin = _admin(client, db_session)
    bootstrap = _issue(client, admin, "ambiguous-host").json()["token"]

    resp = client.post(
        "/api/v1/agents/enroll",
        json={
            "hostname": "ambiguous-host",
            "enrollment_token": enroll_token,
            "bootstrap_token": bootstrap,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ENROLLMENT_MODE_CONFLICT"


def test_bootstrap_mode_disables_legacy_shared_token(client, db_session, enroll_token, monkeypatch):
    from backend.app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "enrollment_mode", "bootstrap")

    resp = _legacy_enroll(client, "legacy-in-secure-profile", enroll_token)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "ENROLLMENT_DISABLED"


def test_bootstrap_mode_still_allows_bootstrap_enrollment(client, db_session, monkeypatch):
    from backend.app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "enrollment_mode", "bootstrap")
    admin = _admin(client, db_session)
    tok = _issue(client, admin, "secure-host").json()["token"]

    resp = _bootstrap_enroll(client, "secure-host", tok)
    assert resp.status_code == 200
    assert resp.json()["host_id"]


def test_legacy_reenroll_does_not_replace_existing_credential(client, enroll_token):
    """F08: the shared secret must not rotate an existing host credential."""
    first = _legacy_enroll(client, "dup-secure", enroll_token)
    assert first.status_code == 200
    first_body = first.json()

    second = _legacy_enroll(client, "dup-secure", enroll_token)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "HOSTNAME_TAKEN"

    # The original credential still authenticates: it was never replaced.
    hb = client.post(
        "/api/v1/agents/heartbeat",
        headers=auth_headers(first_body["host_id"], first_body["agent_token"]),
        json={},
    )
    assert hb.status_code == 200


def test_bootstrap_reenroll_rotates_with_stable_identity(client, db_session):
    """Operator-issued bootstrap is the only supported re-enrollment path."""
    admin = _admin(client, db_session)
    tok1 = _issue(client, admin, "renew-host").json()["token"]
    first = _bootstrap_enroll(client, "renew-host", tok1)
    assert first.status_code == 200
    first_body = first.json()

    tok2 = _issue(client, admin, "renew-host").json()["token"]
    second = _bootstrap_enroll(client, "renew-host", tok2)
    assert second.status_code == 200
    second_body = second.json()

    assert second_body["host_id"] == first_body["host_id"]
    assert second_body["agent_token"] != first_body["agent_token"]

    old = client.post(
        "/api/v1/agents/heartbeat",
        headers=auth_headers(first_body["host_id"], first_body["agent_token"]),
        json={},
    )
    assert old.status_code == 401
