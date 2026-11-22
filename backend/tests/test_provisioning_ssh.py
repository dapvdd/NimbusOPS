"""The browser cannot choose commands, addresses, keys, or trust policy."""

import json

import pytest


def test_custom_ca_crosses_sudo_explicitly(monkeypatch):
    import shlex
    from types import SimpleNamespace
    from backend.app.provisioning.ssh import install

    captured = {}

    def run(argv, **kwargs):
        captured["command"] = argv[-1]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("backend.app.provisioning.ssh._run_install", run)
    target = Target(
        "test",
        "192.0.2.10",
        "installer",
        "new-vm",
        "/key",
        "/known",
        "a" * 32,
        ca_bundle="/etc/nimbusops/enterprise.pem",
    )
    install(target, "https://demo.example", "secret")
    command = shlex.split(captured["command"])
    assert command[:4] == ["sudo", "-n", "bash", "-c"]
    script = command[4]
    assert "--cacert /etc/nimbusops/enterprise.pem" in script
    assert "--ca-bundle /etc/nimbusops/enterprise.pem" in script
    assert "sudo -E" not in script


@pytest.mark.parametrize(
    "path", ["relative.pem", "", "/tmp/ca\n.pem", "/tmp/$(bad)", "/tmp/ca file.pem"]
)
def test_policy_rejects_unsafe_ca_paths(path):
    with pytest.raises(ValueError, match="CA"):
        Target(
            "test",
            "192.0.2.10",
            "installer",
            "new-vm",
            "/key",
            "/known",
            "a" * 32,
            ca_bundle=path,
        )


from backend.app.provisioning.ssh import Target, load_targets, ssh_argv, parse_preflight


def test_install_transport_keeps_token_out_of_argv(monkeypatch):
    from backend.app.provisioning.ssh import install

    captured = {}

    def run(argv, **kwargs):
        from types import SimpleNamespace

        captured.update(argv=argv, **kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("backend.app.provisioning.ssh._run_install", run)
    target = Target(
        "test", "192.0.2.10", "installer", "new-vm", "/run/key", "/etc/known", "a" * 32
    )
    install(target, "https://demo.example", "ephemeral-secret")
    assert "ephemeral-secret" not in str(captured["argv"])
    assert captured["input"] == "ephemeral-secret\n"
    command = captured["argv"][-1]
    from backend.app.provisioning.ssh import AGENT_SHA256

    assert AGENT_SHA256 in command
    assert "--reenroll" not in command
    assert "agent.json" in command


def test_automatic_adapter_moves_only_bootstrap_file_to_memory():
    from backend.app.provisioning.ssh import adapt_installer
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "deploy/agent-install.sh"
    ).read_text()
    adapted = adapt_installer(source)
    assert '"$state/bootstrap.token"' not in adapted
    assert '"$secret/bootstrap.token"' in adapted
    assert "mktemp -d /dev/shm/" in adapted
    assert '"$state/agent.json"' in adapted  # Persistent host identity is unchanged.


def test_missing_policy_disables_automatic_setup(tmp_path):
    assert load_targets(tmp_path / "absent.json") == {}


def test_policy_rejects_duplicate_machine_aliases(tmp_path):
    policy = tmp_path / "targets.json"
    entry = dict(
        address="192.0.2.10",
        username="installer",
        hostname="new-vm",
        identity_file="/run/secrets/install",
        known_hosts="/etc/nimbusops/known_hosts",
        machine_id="a" * 32,
        port=22,
    )
    policy.write_text(json.dumps({"one": entry, "two": entry}))
    with pytest.raises(ValueError):
        load_targets(policy)


def test_ssh_disables_ambient_config_and_requires_pinned_host_key():
    target = Target(
        "test", "192.0.2.10", "installer", "new-vm", "/run/key", "/etc/known", "a" * 32
    )
    argv = ssh_argv(target)
    assert "StrictHostKeyChecking=yes" in argv
    assert "IdentitiesOnly=yes" in argv
    assert "BatchMode=yes" in argv
    assert "PasswordAuthentication=no" in argv
    assert argv[1:3] == ["-F", "none"]


@pytest.mark.parametrize(
    "output",
    [
        "ubuntu\n22.04\nx86_64\nnew-vm\n" + "a" * 32 + "\nclean\n",
        "ubuntu\n24.04\nx86_64\nnew-vm\n" + "a" * 32 + "\nexisting\n",
        "ubuntu\n24.04\nx86_64\nother-vm\n" + "a" * 32 + "\nclean\n",
        "ubuntu\n24.04\nx86_64\nnew-vm\n" + "b" * 32 + "\nclean\n",
    ],
)
def test_preflight_rejects_incompatible_or_changed_identity(output):
    target = Target(
        "test", "192.0.2.10", "installer", "new-vm", "/run/key", "/etc/known", "a" * 32
    )
    with pytest.raises(ValueError):
        parse_preflight(target, output)


@pytest.mark.parametrize("status,installer_status", [(0, 0), (1, 42), (255, None)])
def test_install_keeps_only_fixed_checkpoint_and_numeric_evidence(
    monkeypatch, status, installer_status
):
    from types import SimpleNamespace
    from backend.app.provisioning import ssh

    output = (
        "secret-password\nNIMBUSOPS/1 LOCK_ACQUIRED\nNIMBUSOPS/1 ARCHIVE_VERIFIED\n"
    )
    if installer_status is not None:
        output += f"NIMBUSOPS/1 INSTALLER_EXIT {installer_status}\n"
    output += "NIMBUSOPS/1 secret-token\n"
    monkeypatch.setattr(
        ssh,
        "_run_install",
        lambda *a, **kw: SimpleNamespace(returncode=status, stdout=output),
    )
    target = Target(
        "test", "192.0.2.10", "installer", "new-vm", "/key", "/known", "a" * 32
    )
    if status:
        with pytest.raises(ssh.InstallOutcomeUnknown) as caught:
            ssh.install(target, "https://demo.example", "secret-token")
        evidence = caught.value.evidence
    else:
        evidence = ssh.install(target, "https://demo.example", "secret-token")
    assert evidence.phases == ("LOCK_ACQUIRED", "ARCHIVE_VERIFIED")
    assert evidence.installer_exit_status == installer_status
    assert evidence.transport_exit_status == status
    assert "secret" not in repr(evidence)


def test_timeout_preserves_safe_partial_evidence(monkeypatch):
    import subprocess
    from backend.app.provisioning import ssh

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            "secret-command",
            600,
            output=b"NIMBUSOPS/1 LOCK_ACQUIRED\nsecret-token\n",
            stderr=b"password",
        )

    monkeypatch.setattr(ssh, "_run_install", timeout)
    target = Target(
        "test", "192.0.2.10", "installer", "new-vm", "/key", "/known", "a" * 32
    )
    with pytest.raises(ssh.InstallOutcomeUnknown) as caught:
        ssh.install(target, "https://demo.example", "secret-token")
    assert caught.value.evidence.phases == ("LOCK_ACQUIRED",)
    assert caught.value.evidence.outcome == "TIMED_OUT"
    assert caught.value.evidence.installer_exit_status is None
    assert "secret" not in str(caught.value)


def test_cancellation_is_not_reported_as_remote_rollback(monkeypatch):
    from backend.app.provisioning import ssh

    def cancel(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(ssh, "_run_install", cancel)
    target = Target(
        "test", "192.0.2.10", "installer", "new-vm", "/key", "/known", "a" * 32
    )
    with pytest.raises(ssh.InstallCancelled) as caught:
        ssh.install(target, "https://demo.example", "secret-token")
    assert caught.value.evidence.outcome == "CANCELLED"


def test_bounded_transport_drains_large_output_without_persisting_it():
    import sys
    from backend.app.provisioning.ssh import _run_install

    # Local Python only: no SSH, installer, root, network, or durable output.
    result = _run_install(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdin.readline(); sys.stdout.write('x' * 1000000)",
        ],
        input="test\n",
        timeout=5,
    )
    assert result.returncode == 0
    assert len(result.stdout) == 4096


def test_bounded_transport_timeout_kills_only_local_waiter():
    import subprocess
    import sys
    from backend.app.provisioning.ssh import _run_install

    with pytest.raises(subprocess.TimeoutExpired) as caught:
        _run_install(
            [
                sys.executable,
                "-c",
                "import sys,time; sys.stdout.buffer.write(b'NIMBUSOPS/1 LOCK_ACQUIRED\\n'); sys.stdout.flush(); time.sleep(30)",
            ],
            input="test\n",
            timeout=1,
        )
    assert caught.value.output == b"NIMBUSOPS/1 LOCK_ACQUIRED\n"


def test_protocol_rejects_incomplete_unknown_and_unbounded_numeric_records(monkeypatch):
    from types import SimpleNamespace
    from backend.app.provisioning import ssh

    output = (
        "NIMBUSOPS/1 INSTALLER_EXIT 999\n"
        "NIMBUSOPS/1 INSTALLER_EXIT -1\n"
        "NIMBUSOPS/1 LOCK_ACQUIRED secret-token\n"
        "NIMBUSOPS/1 PASSWORD secret-token\n"
        "x" * 4096 + "\nNIMBUSOPS/1 ARCHIVE_VERIFIED\n"
    )
    monkeypatch.setattr(
        ssh,
        "_run_install",
        lambda *a, **kw: SimpleNamespace(returncode=255, stdout=output),
    )
    target = Target(
        "test", "192.0.2.10", "installer", "new-vm", "/key", "/known", "a" * 32
    )
    with pytest.raises(ssh.InstallOutcomeUnknown) as caught:
        ssh.install(target, "https://demo.example", "secret-token")
    assert caught.value.evidence.phases == ()
    assert caught.value.evidence.installer_exit_status is None
