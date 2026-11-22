"""Fixed read-only SSH preflight. Never accept connection details from HTTP.

Policy and key files must be managed by the service operator, outside the web
root. Passwords, private key contents and remote output are never logged.
"""

import ipaddress
import json
import re
import shlex
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Target:
    id: str
    address: str
    username: str
    hostname: str
    identity_file: str
    known_hosts: str
    machine_id: str
    port: int = 22
    ca_bundle: str | None = None

    def __post_init__(self) -> None:
        if self.ca_bundle is not None and (
            not isinstance(self.ca_bundle, str)
            or not re.fullmatch(r"/[a-zA-Z0-9_./-]+", self.ca_bundle)
            or ".." in self.ca_bundle.split("/")
        ):
            raise ValueError("invalid absolute target CA bundle path")
        ipaddress.ip_address(self.address)  # No DNS rebinding or option injection.
        for value in (self.id, self.username, self.hostname):
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,252}", value):
                raise ValueError("invalid target policy")
        if not re.fullmatch(r"[a-f0-9]{32}", self.machine_id):
            raise ValueError("explicit machine binding required")
        if not 1 <= self.port <= 65535:
            raise ValueError("invalid SSH port")
        for value in (self.identity_file, self.known_hosts):
            if not value.startswith("/") or any(c in value for c in "\r\n\x00"):
                raise ValueError("absolute server-side credential references required")


def load_targets(path: Path) -> dict[str, Target]:
    """Load explicit machine authorization; absent policy disables setup."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    targets = {key: Target(id=key, **value) for key, value in data.items()}
    for attr in ("machine_id", "address", "hostname"):
        values = [getattr(target, attr) for target in targets.values()]
        if len(values) != len(set(values)):
            raise ValueError("duplicate target identity")
    return targets


def ssh_argv(target: Target) -> list[str]:
    """Ignore user SSH config/agent and require pre-provisioned trust."""
    return [
        "ssh",
        "-F",
        "none",
        "-T",
        "-p",
        str(target.port),
        "-i",
        target.identity_file,
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "IdentityAgent=none",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={target.known_hosts}",
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "ForwardAgent=no",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=10",
        "-o",
        "ServerAliveCountMax=2",
        f"{target.username}@{target.address}",
    ]


PREFLIGHT = """set -eu
. /etc/os-release
printf '%s\\n' "$ID" "$VERSION_ID" "$(uname -m)" "$(hostname)" "$(cat /etc/machine-id)"
if sudo -n test -e /var/lib/nimbusops-agent/agent.json; then
  printf 'existing\\n'
else
  sudo -n test ! -e /var/lib/nimbusops-agent/agent.json
  printf 'clean\\n'
fi
"""


def parse_preflight(target: Target, output: str) -> dict[str, str]:
    """Fail closed for existing identity, OS mismatch or changed machine."""
    lines = output.strip().splitlines()
    expected = [
        "ubuntu",
        "24.04",
        "x86_64",
        target.hostname,
        target.machine_id,
        "clean",
    ]
    if lines != expected:
        raise ValueError("PREFLIGHT_IDENTITY_OR_COMPATIBILITY_REJECTED")
    return {
        "hostname": target.hostname,
        "os": "Ubuntu 24.04",
        "architecture": "amd64",
        "machine_id": target.machine_id,
        "identity": "absent",
    }


def preflight(target: Target) -> dict[str, str]:
    """Read target facts with fixed script; discard raw diagnostics."""
    try:
        result = subprocess.run(
            ssh_argv(target) + ["bash -s"],
            input=PREFLIGHT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("SSH_PREFLIGHT_UNAVAILABLE") from None
    if result.returncode:
        raise ValueError("SSH_PREFLIGHT_REJECTED")
    return parse_preflight(target, result.stdout)


AGENT_RELEASE = "nimbusops-agent-1.0.0rc2-fullmvp2-ubuntu24.04-amd64.tar.gz"
AGENT_SHA256 = "72e14b89a3c0dc407dc46398f8474dd38bd6e41cccdb6d06204df8a744554426"


def adapt_installer(source: str) -> str:
    """Adapt the immutable manual installer for stdin and tmpfs bootstrap input."""
    old = "read -r -s -p 'Bootstrap token (hidden): ' token </dev/tty"
    newline = "printf '\\n' >/dev/tty"
    if source.count(old) != 1 or source.count(newline) != 1:
        raise ValueError("INSTALLER_CONTRACT_CHANGED")
    source = source.replace(old, "IFS= read -r token").replace(newline, ":")
    source = source.replace('"$state/bootstrap.token"', '"$secret/bootstrap.token"')
    prefix = """secret=$(mktemp -d /dev/shm/nimbusops-bootstrap.XXXXXX)
chmod 0700 "$secret"
chown nimbusops-agent:nimbusops-agent "$secret"
trap 'rm -rf "$secret"' EXIT
"""
    source = source.replace("IFS= read -r token", prefix + "IFS= read -r token")
    source = source.replace(
        "trap 'rm -f \"$secret/bootstrap.token\"' EXIT",
        "trap 'rm -rf \"$secret\"' EXIT",
    )
    return source


INSTALL_PHASES = (
    "LOCK_ACQUIRED",
    "IDENTITY_ABSENT",
    "ARCHIVE_DOWNLOADED",
    "ARCHIVE_VERIFIED",
    "ARCHIVE_EXTRACTED",
    "ADAPTER_READY",
    "INSTALLER_STARTED",
)
CAPTURE_LIMIT = 4096


@dataclass(frozen=True)
class InstallEvidence:
    """Allowlisted observations, never proof of remote rollback or enrollment."""

    phases: tuple[str, ...] = ()
    installer_exit_status: int | None = None
    transport_exit_status: int | None = None
    outcome: str = "TRANSPORT_FAILED"


def _evidence(
    output: str | bytes | None, status: int | None, outcome: str
) -> InstallEvidence:
    """Drop all text except complete fixed records within a bounded prefix."""
    if isinstance(output, bytes):
        output = output.decode("ascii", errors="replace")
    phases: list[str] = []
    installer_status = None
    for line in (output or "")[:CAPTURE_LIMIT].splitlines(keepends=True):
        if not line.endswith("\n"):
            continue
        record = line[:-1]
        if record.startswith("NIMBUSOPS/1 "):
            value = record[len("NIMBUSOPS/1 ") :]
            if value in INSTALL_PHASES and value not in phases:
                phases.append(value)
            match = re.fullmatch(r"INSTALLER_EXIT ([0-9]{1,3})", value)
            if match and 0 <= int(match[1]) <= 255:
                installer_status = int(match[1])
    return InstallEvidence(tuple(phases), installer_status, status, outcome)


class InstallCancelled(KeyboardInterrupt):
    """Local cancellation stops waiting, not necessarily the remote installer."""

    def __init__(self, evidence: InstallEvidence) -> None:
        super().__init__("INSTALL_CANCELLED_OUTCOME_UNKNOWN")
        self.evidence = evidence


def _run_install(
    argv: list[str], *, input: str, timeout: int
) -> subprocess.CompletedProcess[str]:
    """Drain stdout with bounded memory; never capture stderr or persist raw text."""
    captured = bytearray()
    with subprocess.Popen(
        argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    ) as process:
        assert process.stdout is not None and process.stdin is not None

        def drain() -> None:
            assert process.stdout is not None
            while chunk := process.stdout.read(1024):
                captured.extend(chunk[: max(0, CAPTURE_LIMIT - len(captured))])

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        try:
            try:
                process.stdin.write(input.encode("ascii"))
                process.stdin.close()
            except BrokenPipeError:
                pass
            process.wait(timeout=timeout)
        except BaseException as exc:
            process.kill()
            process.wait()
            reader.join()
            if isinstance(exc, subprocess.TimeoutExpired):
                raise subprocess.TimeoutExpired(
                    "ssh-install", timeout, output=bytes(captured)
                ) from None
            if isinstance(exc, KeyboardInterrupt):
                raise InstallCancelled(
                    _evidence(bytes(captured), None, "CANCELLED")
                ) from None
            raise
        reader.join()
        return subprocess.CompletedProcess(
            argv, process.returncode, captured.decode("ascii", errors="replace")
        )


class InstallOutcomeUnknown(ValueError):
    """Only the transport exit status is safe; it is not proof of remote rollback."""

    def __init__(
        self, exit_status: int | None = None, *, evidence: InstallEvidence | None = None
    ) -> None:
        super().__init__("INSTALL_OUTCOME_UNKNOWN")
        self.evidence = evidence or InstallEvidence(transport_exit_status=exit_status)
        self.exit_status = self.evidence.transport_exit_status


def install(target: Target, origin: str, token: str) -> InstallEvidence:
    """Execute the pinned installer with an explicit noninteractive input adapter.

    The verified archive is immutable. Only its two terminal-input lines are
    adapted, with exact-match assertions, because the existing manual installer
    reads /dev/tty. No new enrollment protocol or credential persistence.
    SSH failures are ambiguous: callers MUST reconcile, never blindly retry.
    """
    if not re.fullmatch(r"https://[a-zA-Z0-9.-]+(?::[0-9]+)?", origin):
        raise ValueError("HTTPS_ORIGIN_REQUIRED")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", token):
        raise ValueError("INVALID_BOOTSTRAP_INPUT")
    import inspect

    ca_download = (
        f" --cacert {shlex.quote(target.ca_bundle)}" if target.ca_bundle else ""
    )
    ca_install = (
        f" --ca-bundle {shlex.quote(target.ca_bundle)}" if target.ca_bundle else ""
    )

    adapter = inspect.getsource(adapt_installer) + """
from pathlib import Path
p = Path("install.sh")
p.write_text(adapt_installer(p.read_text()))
"""
    script = f"""set +x
set -eu
# Only the wrapper can write the protocol channel; installer output is discarded.
exec 3>&1
exec >/dev/null 2>&1
umask 077
exec 9>/run/nimbusops-agent-install.lock
flock -n 9 || exit 73
printf 'NIMBUSOPS/1 LOCK_ACQUIRED\\n' >&3
test ! -e /var/lib/nimbusops-agent/agent.json
printf 'NIMBUSOPS/1 IDENTITY_ABSENT\\n' >&3
IFS= read -r bootstrap
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
curl --fail --silent --show-error --proto '=https' --tlsv1.2{ca_download} {shlex.quote(origin + '/releases/' + AGENT_RELEASE)} -o agent.tar.gz
printf 'NIMBUSOPS/1 ARCHIVE_DOWNLOADED\\n' >&3
printf '%s  %s\\n' {AGENT_SHA256} agent.tar.gz | sha256sum --check --status
printf 'NIMBUSOPS/1 ARCHIVE_VERIFIED\\n' >&3
tar -xzf agent.tar.gz
printf 'NIMBUSOPS/1 ARCHIVE_EXTRACTED\\n' >&3
python3 -c {shlex.quote(adapter)}
printf 'NIMBUSOPS/1 ADAPTER_READY\\n' >&3
printf 'NIMBUSOPS/1 INSTALLER_STARTED\\n' >&3
set +e
printf '%s\\n' "$bootstrap" | bash install.sh {shlex.quote(origin)} {shlex.quote(target.hostname)}{ca_install} 3>&-
installer_status=$?
unset bootstrap
printf 'NIMBUSOPS/1 INSTALLER_EXIT %s\\n' "$installer_status" >&3
exit "$installer_status"
"""
    try:
        result = _run_install(
            ssh_argv(target) + ["sudo -n bash -c " + shlex.quote(script)],
            input=token + "\n",
            timeout=600,
        )
    except subprocess.TimeoutExpired as exc:
        raise InstallOutcomeUnknown(
            evidence=_evidence(exc.output, None, "TIMED_OUT")
        ) from None
    except KeyboardInterrupt as exc:
        if isinstance(exc, InstallCancelled):
            raise
        raise InstallCancelled(InstallEvidence(outcome="CANCELLED")) from None
    except OSError:
        raise InstallOutcomeUnknown() from None
    evidence = _evidence(
        getattr(result, "stdout", None),
        result.returncode,
        "TRANSPORT_FAILED" if result.returncode else "COMPLETED",
    )
    if result.returncode:
        raise InstallOutcomeUnknown(evidence=evidence)
    return evidence
