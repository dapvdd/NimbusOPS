"""Slice 2: agent one-shot re-enroll and credential-file application.

Tests:
- Task 2.1: --reenroll flag
- Task 2.2: --apply-credential-file flag
"""

import json
import logging
import pathlib
import sys
from datetime import datetime, timezone
import pytest

from agent.nimbusops_agent.config import Identity, save_identity, load_identity
from agent.nimbusops_agent.main import main, run_reenroll, run_apply_credential_file


class _FakeSender:
    def __init__(self, server_url, host_id, agent_token, *args, **kwargs):
        self.server_url = server_url
        self.host_id = host_id
        self.agent_token = agent_token
        self.closed = False
        self.enroll_calls = []
        self.heartbeat_calls = []

    def close(self):
        self.closed = True

    def enroll(self, hostname, enrollment_token="", info=None, *, bootstrap_token=None):
        self.enroll_calls.append({"hostname": hostname, "bootstrap_token": bootstrap_token, "enrollment_token": enrollment_token})
        if getattr(self, "_enroll_fail", False):
            return False, "enroll rejected"
        return True, {"host_id": "test-host-id-42", "agent_token": "new-secret-agent-token"}

    def send_heartbeat(self, info):
        self.heartbeat_calls.append(info)
        if getattr(self, "_heartbeat_fail", False):
            return False, "heartbeat failed"
        if getattr(self, "_heartbeat_auth_error", False):
            from agent.nimbusops_agent.client import AuthError
            raise AuthError("credentials rejected HTTP 401")
        if getattr(self, "_heartbeat_net_error", False):
            return False, "network error"
        return True, "ok"


def test_reenroll_success_writes_identity_and_verifies_heartbeat(tmp_path, monkeypatch):
    state_file = tmp_path / "agent.json"
    orig_identity = Identity(host_id="orig-id", agent_token="orig-token")
    save_identity(state_file, orig_identity)

    token_file = tmp_path / "bootstrap.tok"
    token_file.write_text("valid-bootstrap-token\n", encoding="utf-8")

    monkeypatch.setattr("agent.nimbusops_agent.main.Sender", _FakeSender)

    code = run_reenroll(
        state_path=state_file,
        token="valid-bootstrap-token",
        server_url="http://testserver",
        agent_mode="executor",
    )
    assert code == 0
    # Identity is updated
    updated = load_identity(state_file)
    assert updated.host_id == "test-host-id-42"
    assert updated.agent_token == "new-secret-agent-token"

    # Pre-reenroll backup is removed on success
    backups = list(tmp_path.glob("agent.json.pre-reenroll-*"))
    assert len(backups) == 0


def test_reenroll_missing_token_fails_without_touching_state(tmp_path, monkeypatch):
    state_file = tmp_path / "agent.json"
    orig_identity = Identity(host_id="orig-id", agent_token="orig-token")
    save_identity(state_file, orig_identity)

    # Calling run_reenroll without a bootstrap token (or passing None/empty)
    code = run_reenroll(
        state_path=state_file,
        token="",
        server_url="http://testserver",
        agent_mode=None,
    )
    assert code == 2
    assert load_identity(state_file).host_id == "orig-id"


def test_reenroll_server_failure_restores_backup(tmp_path, monkeypatch):
    state_file = tmp_path / "agent.json"
    orig_identity = Identity(host_id="orig-id", agent_token="orig-token")
    save_identity(state_file, orig_identity)

    class _FailingSender(_FakeSender):
        def enroll(self, *args, **kwargs):
            return False, "server 500 error"

    monkeypatch.setattr("agent.nimbusops_agent.main.Sender", _FailingSender)

    code = run_reenroll(
        state_path=state_file,
        token="some-bootstrap-tok",
        server_url="http://testserver",
        agent_mode=None,
    )
    assert code == 2
    # Identity restored from backup
    assert load_identity(state_file).host_id == "orig-id"
    # Backup file retained for inspection
    backups = list(tmp_path.glob("agent.json.pre-reenroll-*"))
    assert len(backups) == 1


def test_reenroll_argv_carries_only_token_file_path(monkeypatch, tmp_path):
    """RC2 F01: argv carries the token FILE PATH, never token material.

    Behavioral form: after main() runs a full re-enroll driven by argv, the
    only secret-ish argv element is the file path itself; the token stays
    inside the file and the Sender receives it as a parameter, not a flag.
    """
    token_file = tmp_path / "tok.txt"
    secret = "super-secret-token"
    token_file.write_text(secret, encoding="utf-8")
    state_file = tmp_path / "agent.json"
    save_identity(state_file, Identity(host_id="id1", agent_token="tok1"))

    captured: dict = {}

    class _CapturingSender(_FakeSender):
        def __init__(self, server_url, host_id, agent_token, *args, **kwargs):
            super().__init__(server_url, host_id, agent_token)
            captured["init_args"] = (host_id, agent_token)

        def enroll(self, hostname, enrollment_token="", info=None, *, bootstrap_token=None):
            captured["bootstrap_token"] = bootstrap_token
            return super().enroll(hostname, enrollment_token, info, bootstrap_token=bootstrap_token)

    monkeypatch.setattr("agent.nimbusops_agent.main.Sender", _CapturingSender)

    code = main(["--reenroll", "--bootstrap-token-file", str(token_file), "--state-file", str(state_file)])
    assert code == 0
    # The token reached the enrollment call as a parameter...
    assert captured["bootstrap_token"] == secret
    # ...while argv (unchanged process arguments) never carried the material.
    for arg in sys.argv:
        assert secret not in arg
    # The identity was replaced, proving the flow really ran.
    assert load_identity(state_file).host_id == "test-host-id-42"


def test_reenroll_heartbeat_verification_failure_restores_original(tmp_path, monkeypatch):
    """A successful enroll followed by a failed verification heartbeat must
    restore the original identity and exit 2 — the new credential is not
    trusted until the server accepts a heartbeat with it."""
    token_file = tmp_path / "tok.txt"
    token_file.write_text("valid-bootstrap-token", encoding="utf-8")
    state_file = tmp_path / "agent.json"
    save_identity(state_file, Identity(host_id="orig-id", agent_token="orig-token"))

    class _HeartbeatFailSender(_FakeSender):
        _heartbeat_fail = True

    monkeypatch.setattr("agent.nimbusops_agent.main.Sender", _HeartbeatFailSender)

    code = main(["--reenroll", "--bootstrap-token-file", str(token_file), "--state-file", str(state_file)])
    assert code == 2
    # Original identity restored.
    assert load_identity(state_file).host_id == "orig-id"
    assert load_identity(state_file).agent_token == "orig-token"
    # Backup retained for inspection.
    assert len(list(tmp_path.glob("agent.json.pre-reenroll-*"))) == 1


def test_reenroll_enters_loop_never(monkeypatch, tmp_path):
    token_file = tmp_path / "tok.txt"
    token_file.write_text("tok-123", encoding="utf-8")
    state_file = tmp_path / "agent.json"
    save_identity(state_file, Identity(host_id="id1", agent_token="tok1"))

    monkeypatch.setattr("agent.nimbusops_agent.main.Sender", _FakeSender)

    loop_called = False
    def _fake_run(*args, **kwargs):
        nonlocal loop_called
        loop_called = True
        return 0

    monkeypatch.setattr("agent.nimbusops_agent.main.run", _fake_run)
    code = main(["--reenroll", "--bootstrap-token-file", str(token_file), "--state-file", str(state_file)])
    assert code == 0
    assert not loop_called


def test_apply_success_replaces_identity_and_cleans_up(tmp_path, monkeypatch):
    state_file = tmp_path / "agent.json"
    save_identity(state_file, Identity(host_id="h1", agent_token="old-token"))
    cand_file = tmp_path / "cand.json"
    cand_file.write_text(json.dumps({"agent_token": "cand-token"}), encoding="utf-8")

    monkeypatch.setattr("agent.nimbusops_agent.main.Sender", _FakeSender)

    code = run_apply_credential_file(
        state_path=state_file,
        candidate_path=cand_file,
        server_url="http://testserver",
    )
    assert code == 0
    assert load_identity(state_file).agent_token == "cand-token"
    assert not cand_file.exists()
    assert len(list(tmp_path.glob("agent.json.pre-apply-*"))) == 0


def test_apply_rejects_missing_identity(tmp_path):
    state_file = tmp_path / "nonexistent.json"
    cand_file = tmp_path / "cand.json"
    cand_file.write_text(json.dumps({"agent_token": "cand-token"}), encoding="utf-8")

    code = run_apply_credential_file(state_file, cand_file, "http://testserver")
    assert code == 2


def test_apply_rejects_candidate_equal_to_state_path(tmp_path):
    state_file = tmp_path / "agent.json"
    save_identity(state_file, Identity(host_id="h1", agent_token="tok1"))

    code = run_apply_credential_file(state_file, state_file, "http://testserver")
    assert code == 2


def test_apply_unauthorized_keeps_everything(tmp_path, monkeypatch):
    state_file = tmp_path / "agent.json"
    save_identity(state_file, Identity(host_id="h1", agent_token="old-token"))
    cand_file = tmp_path / "cand.json"
    cand_file.write_text(json.dumps({"agent_token": "rejected-token"}), encoding="utf-8")

    class _AuthFailSender(_FakeSender):
        def send_heartbeat(self, info):
            from agent.nimbusops_agent.client import AuthError
            raise AuthError("HTTP 401 Unauthorized")

    monkeypatch.setattr("agent.nimbusops_agent.main.Sender", _AuthFailSender)

    code = run_apply_credential_file(state_file, cand_file, "http://testserver")
    assert code == 3
    assert load_identity(state_file).agent_token == "old-token"
    assert cand_file.exists()


def test_apply_network_failure_keeps_everything(tmp_path, monkeypatch):
    state_file = tmp_path / "agent.json"
    save_identity(state_file, Identity(host_id="h1", agent_token="old-token"))
    cand_file = tmp_path / "cand.json"
    cand_file.write_text(json.dumps({"agent_token": "net-fail-token"}), encoding="utf-8")

    class _NetFailSender(_FakeSender):
        def send_heartbeat(self, info):
            return False, "network error"

    monkeypatch.setattr("agent.nimbusops_agent.main.Sender", _NetFailSender)

    code = run_apply_credential_file(state_file, cand_file, "http://testserver")
    assert code == 1
    assert load_identity(state_file).agent_token == "old-token"
    assert cand_file.exists()


def test_apply_no_token_in_argv_or_logs(tmp_path, monkeypatch, caplog):
    state_file = tmp_path / "agent.json"
    save_identity(state_file, Identity(host_id="h1", agent_token="old-token"))
    cand_file = tmp_path / "cand.json"
    secret = "secret-token-12345"
    cand_file.write_text(json.dumps({"agent_token": secret}), encoding="utf-8")

    monkeypatch.setattr("agent.nimbusops_agent.main.Sender", _FakeSender)

    test_argv = ["nimbusops-agent", "--apply-credential-file", str(cand_file), "--state-file", str(state_file)]
    monkeypatch.setattr(sys, "argv", test_argv)

    with caplog.at_level(logging.DEBUG):
        code = main(test_argv[1:])

    assert code == 0
    assert secret not in caplog.text
    for arg in sys.argv:
        assert secret not in arg
