"""The reviewed source and both download pins bind the new immutable release."""

import hashlib
import tarfile
from pathlib import Path

from backend.app.provisioning.ssh import AGENT_RELEASE, AGENT_SHA256


def test_release_pins_and_sources_match():
    root = Path(__file__).resolve().parents[2]
    archive = root / "frontend/public/releases" / AGENT_RELEASE
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == AGENT_SHA256
    frontend = (root / "frontend/src/lib/agentCommands.ts").read_text()
    assert AGENT_RELEASE in frontend
    assert AGENT_SHA256 in frontend
    with tarfile.open(archive) as bundle:
        for name, source in [
            ("install.sh", "deploy/agent-install.sh"),
            ("prepare-ca.py", "deploy/prepare-ca.py"),
        ]:
            assert bundle.extractfile(name).read() == (
                root / source
            ).read_bytes().replace(b"\r\n", b"\n")
        for source in (root / "agent/nimbusops_agent").glob("*.py"):
            assert bundle.extractfile(
                f"nimbusops_agent/{source.name}"
            ).read() == source.read_bytes().replace(b"\r\n", b"\n")
    old = (
        root
        / "frontend/public/releases/nimbusops-agent-1.0.0rc2-dualmode1-ubuntu24.04-amd64.tar.gz"
    )
    assert (
        hashlib.sha256(old.read_bytes()).hexdigest()
        == "8f0a715761aff04920201409c95d648450329d68acb1e41a616c5e131637d7d9"
    )
    previous = (
        root
        / "frontend/public/releases/nimbusops-agent-1.0.0rc2-dualmode2-ubuntu24.04-amd64.tar.gz"
    )
    assert (
        hashlib.sha256(previous.read_bytes()).hexdigest()
        == "cf2bced62d522473af86dd623458835711957dec25d8ab8c0aac501616a3f2c1"
    )
