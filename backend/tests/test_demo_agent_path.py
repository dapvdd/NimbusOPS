"""Real agent collectors through isolated ASGI control plane (not Ubuntu E2E)."""
from backend.tests.test_bootstrap_enrollment import _admin, _issue
from nimbusops_agent.client import Sender
from nimbusops_agent.config import Config, load_identity
from nimbusops_agent.main import ensure_enrolled, run_cycle


def test_real_agent_telemetry_and_stable_id_after_remove_readd(client, db_session, tmp_path, monkeypatch):
    import nimbusops_agent.main as main

    admin = _admin(client, db_session)
    headers = {"Authorization": f"Bearer {admin}"}
    hostname = "scratch-demo.example.org"

    def factory(**kwargs):
        sender = Sender(**kwargs)
        sender._client.close()
        sender._client = client
        sender.close = lambda: None
        return sender

    monkeypatch.setattr(main, "Sender", factory)
    monkeypatch.setattr(main.socket, "gethostname", lambda: "different-short-name")
    issued = _issue(client, admin, hostname)
    assert issued.status_code == 201
    cfg = Config(server_url="http://testserver", enrollment_token="", bootstrap_token=issued.json()["token"], hostname=hostname, state_file=tmp_path / "agent.json", telemetry_only=True)
    identity, created = ensure_enrolled(cfg)
    assert created
    assert load_identity(cfg.state_file).host_id == identity.host_id

    def assert_fresh(identity):
        sender = factory(server_url="http://testserver", host_id=identity.host_id, agent_token=identity.agent_token)
        ok, detail = run_cycle(sender, telemetry_only=True)
        assert ok, detail
        response = client.get(f"/api/v1/hosts/{identity.host_id}", headers=headers)
        assert response.status_code == 200, response.text
        host = response.json()
        assert host["hostname"] == hostname
        assert host["status"] == "ONLINE"
        assert host["last_seen_at"]
        assert host["last_telemetry_at"]
        assert host["latest_metrics"]

    assert_fresh(identity)
    removed = client.delete(f"/api/v1/hosts/{identity.host_id}", headers=headers)
    assert removed.status_code == 200, removed.text
    reenroll = client.post(f"/api/v1/hosts/{identity.host_id}/re-enroll", headers=headers, json={"new_bootstrap_token": True})
    assert reenroll.status_code == 201, reenroll.text
    cfg.bootstrap_token = reenroll.json()["bootstrap_token"]
    cfg.state_file.unlink()
    replacement, created = ensure_enrolled(cfg)
    assert created and replacement.host_id == identity.host_id
    assert replacement.agent_token != identity.agent_token
    assert_fresh(replacement)
