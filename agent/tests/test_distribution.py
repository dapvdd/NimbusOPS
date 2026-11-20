"""Distribution contracts; Linux execution is a separate acceptance gate."""
import hashlib
import importlib.util
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_release_builder_is_deterministic_and_includes_installer(tmp_path):
    spec = importlib.util.spec_from_file_location("release", ROOT / "deploy/build_agent_release.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    (wheels / "example-1.0-py3-none-any.whl").write_bytes(b"fixture-not-an-installable-wheel")
    first = module.build_release(ROOT, wheels, tmp_path / "one.tar.gz")
    second = module.build_release(ROOT, wheels, tmp_path / "two.tar.gz")
    assert first == second == hashlib.sha256((tmp_path / "one.tar.gz").read_bytes()).hexdigest()
    with tarfile.open(tmp_path / "one.tar.gz") as archive:
        assert "install.sh" in archive.getnames()
        assert "nimbusops_agent/main.py" in archive.getnames()
        assert not any("__pycache__" in name for name in archive.getnames())


def test_installer_private_token_and_offline_dependencies():
    text = (ROOT / "deploy/agent-install.sh").read_text()
    assert 'read -r -s' in text and '/dev/tty' in text
    assert '--no-index' in text and '--require-hashes' in text
    assert '--hostname' in text and '--telemetry-only' in text
    assert 'User=nimbusops-agent' in text
    assert 'set +x' in text
    assert '--bootstrap-token ' not in text


def test_runtime_permissions_and_post_registration_recovery():
    text = (ROOT / "deploy/agent-install.sh").read_text()
    assert 'chmod -R a+rX,go-w "$target"' in text
    assert 'if ! runuser' in text
    assert '[[ -s $state/agent.json ]] || exit 1' in text
    assert 'Registration saved; service will retry telemetry' in text
