"""No SSH or installer runs: transport diagnostics discard all remote output."""

import subprocess
from types import SimpleNamespace

import pytest

from backend.app.provisioning import ssh


def _target() -> ssh.Target:
    return ssh.Target(
        "test", "192.0.2.1", "installer", "vm", "/key", "/known", "a" * 32
    )


@pytest.mark.parametrize("status", [1, 73, 255, -9])
def test_failed_transport_preserves_only_numeric_status(monkeypatch, status):
    seen: dict[str, object] = {}

    def run(argv, *, input, timeout):
        seen["argv"] = argv
        seen["input"] = input
        seen["timeout"] = timeout
        return SimpleNamespace(
            returncode=status,
            stdout="NIMBUSOPS/1 LOCK_ACQUIRED\nnever-print-me\n",
        )

    monkeypatch.setattr(ssh, "_run_install", run)
    with pytest.raises(ValueError) as caught:
        ssh.install(_target(), "https://demo.example", "never-print-me")
    assert caught.value.exit_status == status
    assert str(caught.value) == "INSTALL_OUTCOME_UNKNOWN"
    assert "never-print-me" not in repr(caught.value)
    assert "never-print-me" not in str(seen["argv"])
    assert seen["input"] == "never-print-me\n"
    assert seen["timeout"] == 600


@pytest.mark.parametrize(
    "error", [OSError("private-path"), subprocess.TimeoutExpired("secret-command", 600)]
)
def test_timeout_or_spawn_error_has_no_fabricated_exit_status(monkeypatch, error):
    def run(*args, **kwargs):
        raise error

    monkeypatch.setattr(ssh, "_run_install", run)
    with pytest.raises(ssh.InstallOutcomeUnknown) as caught:
        ssh.install(_target(), "https://demo.example", "never-print-me")
    assert caught.value.exit_status is None
    assert str(caught.value) == "INSTALL_OUTCOME_UNKNOWN"
    assert "never-print-me" not in repr(caught.value)
