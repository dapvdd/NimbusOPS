"""Fixed read-only SSH preflight. Never accept connection details from HTTP.

Policy and key files must be managed by the service operator, outside the web
root. Passwords, private key contents and remote output are never logged.
"""

import ipaddress
import json
import re
import shlex
import subprocess
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

    def __post_init__(self) -> None:
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


AGENT_RELEASE = "nimbusops-agent-1.0.0rc2-dualmode1-ubuntu24.04-amd64.tar.gz"
AGENT_SHA256 = "8f0a715761aff04920201409c95d648450329d68acb1e41a616c5e131637d7d9"


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


def install(target: Target, origin: str, token: str) -> None:
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

    adapter = inspect.getsource(adapt_installer) + """
from pathlib import Path
p = Path("install.sh")
p.write_text(adapt_installer(p.read_text()))
"""
    script = f"""set +x
set -eu
umask 077
exec 9>/run/nimbusops-agent-install.lock
flock -n 9 || exit 73
test ! -e /var/lib/nimbusops-agent/agent.json
IFS= read -r bootstrap
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
curl --fail --silent --show-error --proto '=https' --tlsv1.2 {shlex.quote(origin + '/releases/' + AGENT_RELEASE)} -o agent.tar.gz
printf '%s  %s\\n' {AGENT_SHA256} agent.tar.gz | sha256sum --check --status
tar -xzf agent.tar.gz
python3 -c {shlex.quote(adapter)}
printf '%s\\n' "$bootstrap" | bash install.sh {shlex.quote(origin)} {shlex.quote(target.hostname)}
unset bootstrap
"""
    try:
        result = subprocess.run(
            ssh_argv(target) + ["sudo -n bash -c " + shlex.quote(script)],
            input=token + "\n",
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=600,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("INSTALL_OUTCOME_UNKNOWN") from None
    if result.returncode:
        raise ValueError("INSTALL_OUTCOME_UNKNOWN")
