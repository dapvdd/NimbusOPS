"""New immutable artifacts reuse dependency bytes without replacing old files."""

import tarfile

import pytest


def test_rebuild_preserves_original_and_matches_current_source(tmp_path):
    from deploy.rebuild_agent_release import rebuild

    root = tmp_path / "repo"
    (root / "agent/nimbusops_agent").mkdir(parents=True)
    (root / "agent/nimbusops_agent/main.py").write_bytes(b"# current\n")
    (root / "deploy").mkdir()
    for name in ("agent-install.sh", "prepare-ca.py"):
        (root / "deploy" / name).write_bytes(b"# installer\n")
    from deploy.build_agent_release import build_release

    wheels = tmp_path / "wheels"
    wheels.mkdir()
    (wheels / "example-1.0-py3-none-any.whl").write_bytes(b"dependency")
    original = tmp_path / "original.tar.gz"
    build_release(root, wheels, original)
    before = original.read_bytes()
    (root / "agent/nimbusops_agent/main.py").write_bytes(b"# repaired\n")
    output = tmp_path / "new.tar.gz"
    rebuild(root, original, output)
    assert original.read_bytes() == before
    with tarfile.open(output) as archive:
        assert archive.extractfile("nimbusops_agent/main.py").read() == b"# repaired\n"
        assert (
            archive.extractfile("wheels/example-1.0-py3-none-any.whl").read()
            == b"dependency"
        )
    with pytest.raises(FileExistsError):
        rebuild(root, original, output)
