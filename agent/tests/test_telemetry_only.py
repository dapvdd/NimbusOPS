"""Telemetry-only must never cross the Docker execution boundary."""
from unittest.mock import Mock

import pytest

from nimbusops_agent import main
from nimbusops_agent.config import Config, Identity


def test_cycle_telemetry_only_skips_docker_and_worker(monkeypatch):
    from nimbusops_agent import docker_exec

    executor = Mock(side_effect=AssertionError("Docker accessed"))
    monkeypatch.setattr(docker_exec, "DockerExecutor", executor)
    worker = Mock()
    sender = Mock()
    sender.send_heartbeat.return_value = (True, "ok")
    sender.send_telemetry.return_value = (True, "ok")
    assert main.run_cycle(sender, worker, telemetry_only=True)[0]
    executor.assert_not_called()
    worker.poll_once.assert_not_called()
    info = sender.send_heartbeat.call_args.args[0]
    assert "inventory" not in info
    metrics = sender.send_telemetry.call_args.args[0]
    assert 0 <= metrics["cpu_percent"] <= 100
    assert metrics["memory_total_bytes"] > 0
    assert metrics["disk_total_bytes"] > 0


@pytest.mark.parametrize("reject", [False, True])
def test_run_telemetry_only_no_executor_or_worker(monkeypatch, tmp_path, reject):
    from nimbusops_agent import docker_exec
    from nimbusops_agent.client import AuthError

    cfg = Config(server_url="http://test", enrollment_token="test",
                 state_file=tmp_path / "agent.json", telemetry_only=True)
    monkeypatch.setattr(main, "install_signal_handlers", lambda: None)
    monkeypatch.setattr(main, "ensure_enrolled", lambda _: (Identity("h", "t"), False))
    executor = Mock(side_effect=AssertionError("Docker accessed"))
    worker = Mock(side_effect=AssertionError("worker constructed"))
    monkeypatch.setattr(docker_exec, "DockerExecutor", executor)
    monkeypatch.setattr(main, "CommandWorker", worker)
    sender = Mock()
    def heartbeat(info):
        main._stop["requested"] = True
        if reject:
            raise AuthError("rejected")
        return True, "ok"
    sender.send_heartbeat.side_effect = heartbeat
    sender.send_telemetry.return_value = (True, "ok")
    monkeypatch.setattr(main, "Sender", lambda **kw: sender)
    main._stop["requested"] = False
    try:
        assert main.run(cfg) == (3 if reject else 0)
    finally:
        main._stop["requested"] = False
    executor.assert_not_called()
    worker.assert_not_called()
    sender.close.assert_called_once()


@pytest.mark.parametrize("flag", [False, True])
def test_cli_telemetry_only_opt_in(monkeypatch, tmp_path, flag):
    monkeypatch.delenv("NIMBUSOPS_AGENT_BOOTSTRAP_TOKEN", raising=False)
    captured = []
    monkeypatch.setattr(main, "run", lambda cfg: captured.append(cfg) or 0)
    args = ["--enrollment-token", "test", "--state-file", str(tmp_path / "a.json")]
    assert main.main(args + (["--telemetry-only"] if flag else [])) == 0
    assert captured[0].telemetry_only is flag
