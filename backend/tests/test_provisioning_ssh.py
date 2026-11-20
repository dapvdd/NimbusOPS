"""The browser cannot choose commands, addresses, keys, or trust policy."""

import json

import pytest

from backend.app.provisioning.ssh import Target, load_targets, ssh_argv, parse_preflight


def test_install_transport_keeps_token_out_of_argv(monkeypatch):
    from backend.app.provisioning.ssh import install

    captured = {}

    def run(argv, **kwargs):
        from types import SimpleNamespace

        captured.update(argv=argv, **kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("backend.app.provisioning.ssh.subprocess.run", run)
    target = Target(
        "test", "192.0.2.10", "installer", "new-vm", "/run/key", "/etc/known", "a" * 32
    )
    install(target, "https://demo.example", "ephemeral-secret")
    assert "ephemeral-secret" not in str(captured["argv"])
    assert captured["input"] == "ephemeral-secret\n"
    command = captured["argv"][-1]
    assert "8f0a715761aff04920201409c95d648450329d68acb1e41a616c5e131637d7d9" in command
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
