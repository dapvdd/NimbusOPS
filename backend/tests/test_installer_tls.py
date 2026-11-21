"""Release installer TLS contract, including fail-before-mutation ordering."""
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "deploy/agent-install.sh"


def test_installer_explicit_ca_persistence_and_enrollment():
    source = SOURCE.read_text()
    assert "--ca-bundle)" in source
    assert 'python3 "$bundle/prepare-ca.py" "$ca_bundle"' in source
    assert source.index('python3 "$bundle/prepare-ca.py"') < source.index("apt-get update")
    assert 'runuser -u nimbusops-agent -- test -r "$persisted_ca"' in source
    assert source.count('"${tls_args[@]}"') == 2
    assert 'tls_args=(--ca-bundle "$persisted_ca")' in source
    assert 'ExecStart=$target/venv/bin/python -m nimbusops_agent $tls_service' in source
    assert 'tls_service="--ca-bundle $persisted_ca"' in source


def test_default_has_no_custom_ca_arguments():
    source = SOURCE.read_text()
    assert "tls_args=()" in source
    assert "tls_service=''" in source
    assert 'if [[ -n $ca_bundle ]]; then' in source
