"""Build a reproducible Ubuntu 24.04 amd64 agent bundle from pinned wheels.

Download wheels first using the command in the operator runbook. No credentials
or checkout metadata enter the bundle. The printed digest pins the whole bundle.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import tarfile
from pathlib import Path


def build_release(root: Path, wheels: Path, output: Path) -> str:
    """Write deterministic archive and return its SHA-256 hex digest."""
    entries: dict[str, bytes] = {}
    for path in sorted((root / "agent/nimbusops_agent").glob("*.py")):
        entries[f"nimbusops_agent/{path.name}"] = path.read_bytes().replace(b"\r\n", b"\n")
    entries["install.sh"] = (root / "deploy/agent-install.sh").read_bytes().replace(b"\r\n", b"\n")
    entries["prepare-ca.py"] = (root / "deploy/prepare-ca.py").read_bytes().replace(b"\r\n", b"\n")
    requirements = []
    for wheel in sorted(wheels.glob("*.whl")):
        data = wheel.read_bytes()
        entries[f"wheels/{wheel.name}"] = data
        name, version = wheel.name.split("-")[:2]
        requirements.append(f"{name}=={version} --hash=sha256:{hashlib.sha256(data).hexdigest()}")
    if not requirements:
        raise ValueError("wheelhouse is empty")
    entries["requirements.lock"] = ("\n".join(requirements) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for name, data in sorted(entries.items()):
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    info.mode = 0o755 if name == "install.sh" else 0o644
                    archive.addfile(info, io.BytesIO(data))
    return hashlib.sha256(output.read_bytes()).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(build_release(Path(__file__).resolve().parents[1], args.wheels, args.output))
