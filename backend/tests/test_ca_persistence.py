"""Execute persistence under the installer's restrictive umask."""
import importlib.util
import os
from pathlib import Path
import stat
import ssl

import certifi
import pytest


spec = importlib.util.spec_from_file_location("prepare_ca", Path(__file__).resolve().parents[2] / "deploy/prepare-ca.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.mark.skipif(os.name == "nt", reason="POSIX installer permissions")
def test_persist_is_traversable_under_restrictive_umask(tmp_path, monkeypatch):
    directory = tmp_path / "config"
    monkeypatch.setattr(helper, "CONFIG_DIR", directory, raising=False)
    # Unprivileged sandbox models ownership checks; real modes/umask/replace run.
    monkeypatch.setattr(helper, "ROOT_UID", os.getuid(), raising=False)
    previous = os.umask(0o077)
    try:
        helper.persist_bundle(Path(certifi.where()).read_bytes())
    finally:
        os.umask(previous)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o755
    bundle = directory / "ca-bundle.pem"
    assert stat.S_IMODE(bundle.stat().st_mode) == 0o644
    assert bundle.read_bytes() == Path(certifi.where()).read_bytes()
    assert list(directory.iterdir()) == [bundle]
    context = ssl.create_default_context(cafile=str(bundle))
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED


@pytest.mark.skipif(os.name == "nt", reason="POSIX installer permissions")
@pytest.mark.parametrize("kind", ["private", "writable", "symlink"])
def test_unsafe_persistence_directory_rejected(tmp_path, monkeypatch, kind):
    directory = tmp_path / "config"
    directory.mkdir(mode=0o755)
    if kind == "symlink":
        link = tmp_path / "link"
        link.symlink_to(directory)
        directory = link
    else:
        directory.chmod(0o700 if kind == "private" else 0o777)
    monkeypatch.setattr(helper, "CONFIG_DIR", directory)
    monkeypatch.setattr(helper, "ROOT_UID", os.getuid())
    with pytest.raises(ValueError):
        helper.persist_bundle(b"irrelevant")


@pytest.mark.skipif(os.name == "nt", reason="POSIX installer permissions")
@pytest.mark.parametrize("kind", ["valid", "symlink", "writable", "malformed", "missing", "private-key"])
def test_invalid_sources_fail_without_persisting(tmp_path, monkeypatch, kind):
    # Stop parent traversal at sandbox root without changing real filesystem.
    source = tmp_path / "source.pem"
    source.write_bytes(Path(certifi.where()).read_bytes())
    source.chmod(0o600)
    monkeypatch.setattr(helper, "ROOT_UID", os.getuid())
    original_lstat = Path.lstat
    def lstat(path):
        info = original_lstat(path)
        if path in source.parents:
            values = list(info)
            values[0] = stat.S_IFDIR | 0o755
            values[4] = os.getuid()
            return os.stat_result(values)
        return info
    monkeypatch.setattr(Path, "lstat", lstat)
    if kind == "symlink":
        link = tmp_path / "link.pem"
        link.symlink_to(source)
        source = link
    elif kind == "writable":
        source.chmod(0o666)
    elif kind == "malformed":
        source.write_text("not PEM")
    elif kind == "missing":
        source.unlink()
    elif kind == "private-key":
        source.write_bytes(source.read_bytes() + b"\nPRIVATE KEY")
    if kind == "valid":
        assert helper.checked_bundle(str(source)) == source.read_bytes()
    else:
        with pytest.raises((OSError, ValueError)):
            helper.checked_bundle(str(source))
