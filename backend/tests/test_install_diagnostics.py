"""No SSH or installer runs: transport diagnostics discard all remote output."""

import subprocess
from types import SimpleNamespace

import pytest

from backend.app.provisioning import ssh


@pytest.mark.parametrize("status", [1, 73, 255, -9])
def test_failed_transport_preserves_only_numeric_status(monkeypatch, status):
    def run(*args, **kwargs):
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL
        return SimpleNamespace(returncode=status)

    monkeypatch.setattr(ssh.subprocess, "run", run)
    target = ssh.Target(
        "test", "192.0.2.1", "installer", "vm", "/key", "/known", "a" * 32
    )
    with pytest.raises(ValueError) as caught:
        ssh.install(target, "https://demo.example", "never-print-me")
    assert getattr(caught.value, "exit_status", None) == status
    assert str(caught.value) == "INSTALL_OUTCOME_UNKNOWN"
    assert "never-print-me" not in repr(caught.value)


@pytest.mark.parametrize(
    "error", [OSError("private-path"), subprocess.TimeoutExpired("secret-command", 600)]
)
def test_timeout_or_spawn_error_has_no_fabricated_exit_status(monkeypatch, error):
    def run(*args, **kwargs):
        raise error

    monkeypatch.setattr(ssh.subprocess, "run", run)
    target = ssh.Target(
        "test", "192.0.2.1", "installer", "vm", "/key", "/known", "a" * 32
    )
    with pytest.raises(ssh.InstallOutcomeUnknown) as caught:
        ssh.install(target, "https://demo.example", "never-print-me")
    assert caught.value.exit_status is None
    assert str(caught.value) == "INSTALL_OUTCOME_UNKNOWN"
