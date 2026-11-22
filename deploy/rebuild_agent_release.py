"""Build a new immutable release using an existing archive's dependency bytes."""

from __future__ import annotations

import argparse
import tarfile
import tempfile
from pathlib import Path

from deploy.build_agent_release import build_release


def rebuild(root: Path, source: Path, output: Path) -> str:
    """Reuse flat wheel members without extracting paths or replacing releases."""
    if output.exists():
        raise FileExistsError("immutable release output already exists")
    with tempfile.TemporaryDirectory(prefix="nimbusops-wheelhouse-") as scratch:
        wheels = Path(scratch)
        with tarfile.open(source) as archive:
            for member in archive.getmembers():
                parts = member.name.split("/")
                if (
                    len(parts) == 2
                    and parts[0] == "wheels"
                    and parts[1].endswith(".whl")
                    and member.isfile()
                    and "\\" not in parts[1]
                ):
                    stream = archive.extractfile(member)
                    assert stream is not None
                    (wheels / parts[1]).write_bytes(stream.read())
        return build_release(root, wheels, output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(rebuild(Path(__file__).resolve().parents[1], args.source, args.output))
