"""Validate operator-provisioned trust, optionally persist it for the service.

Only public PEM certificates belong here. Source and its ancestors must be
root-controlled; symlinks and group/world-writable paths are rejected.
"""
import os
from pathlib import Path
import re
import ssl
import stat
import sys
import tempfile

CONFIG_DIR = Path("/etc/nimbusops-agent")
ROOT_UID = 0


def checked_bundle(source: str) -> bytes:
    path = Path(source)
    if not re.fullmatch(r"/[a-zA-Z0-9_./-]+", source) or ".." in path.parts:
        raise ValueError("invalid absolute CA bundle path")
    for entry in (path, *path.parents):
        info = entry.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != ROOT_UID or info.st_mode & 0o022:
            raise ValueError("CA bundle path must be root-controlled")
    if not path.is_file():
        raise ValueError("CA bundle must be a regular file")
    data = path.read_bytes()
    if b"PRIVATE KEY" in data:
        raise ValueError("CA bundle must not contain private keys")
    context = ssl.create_default_context(cadata=data.decode("ascii"))
    if not context.cert_store_stats()["x509_ca"]:
        raise ValueError("CA bundle has no CA certificates")
    return data


def persist_bundle(data: bytes) -> None:
    directory = CONFIG_DIR
    created = False
    if not directory.exists() and not directory.is_symlink():
        directory.mkdir(mode=0o755)
        created = True
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != ROOT_UID or info.st_mode & 0o022:
        raise ValueError("unsafe CA configuration directory")
    if created:
        directory.chmod(0o755)
    elif stat.S_IMODE(info.st_mode) != 0o755:
        raise ValueError("CA configuration directory must have mode 0755")
    destination = directory / "ca-bundle.pem"
    fd, name = tempfile.mkstemp(prefix=".ca-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o644)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, destination)
    finally:
        if os.path.exists(name):
            os.unlink(name)


if __name__ == "__main__":
    try:
        if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != "--persist"):
            raise ValueError("invalid CA helper options")
        data = checked_bundle(sys.argv[1])
        if len(sys.argv) == 3:
            persist_bundle(data)
    except (OSError, ValueError) as exc:
        print(f"Invalid CA configuration: {type(exc).__name__}", file=sys.stderr)
        sys.exit(2)
