#!/usr/bin/env bash
# Invoked only AFTER the operator verifies the containing archive's SHA-256.
set +x
set -euo pipefail
umask 077
if [[ $EUID != 0 || $# -lt 2 || $# -gt 3 ]]; then
  echo 'Usage: sudo bash install.sh https://control-plane exact-hostname [--reenroll]' >&2
  exit 2
fi
server=$1
hostname=$2
reenroll=${3:-}
[[ $server =~ ^https://[a-zA-Z0-9.-]+(:[0-9]+)?$ ]] || { echo 'HTTPS origin required' >&2; exit 2; }
[[ $hostname =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}[a-zA-Z0-9]$ ]] || { echo 'Invalid hostname' >&2; exit 2; }
[[ -z $reenroll || $reenroll == --reenroll ]] || exit 2
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $(uname -m) == x86_64 ]] || { echo 'Ubuntu 24.04 amd64 required' >&2; exit 2; }
bundle=$(cd -- "$(dirname -- "$0")" && pwd)
state=/var/lib/nimbusops-agent
target=/opt/nimbusops-agent
if [[ -f $state/agent.json && $reenroll != --reenroll ]]; then
  echo 'Existing identity: explicitly confirm re-enrollment in dashboard and pass --reenroll.' >&2
  exit 2
fi
apt-get update
apt-get install -y python3 python3-venv ca-certificates
id nimbusops-agent >/dev/null 2>&1 || useradd --system --home-dir "$state" --shell /usr/sbin/nologin nimbusops-agent
install -d -m 0700 -o nimbusops-agent -g nimbusops-agent "$state"
install -d -m 0755 "$target"
python3 -m venv "$target/venv"
"$target/venv/bin/pip" install --no-index --find-links "$bundle/wheels" --require-hashes -r "$bundle/requirements.lock"
site=$("$target/venv/bin/python" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
cp -r "$bundle/nimbusops_agent" "$site/"
chmod -R a+rX,go-w "$target"
read -r -s -p 'Bootstrap token (hidden): ' token </dev/tty
printf '\n' >/dev/tty
[[ -n $token ]] || { echo 'Empty token' >&2; exit 2; }
printf '%s' "$token" > "$state/bootstrap.token"
unset token
chown nimbusops-agent:nimbusops-agent "$state/bootstrap.token"
trap 'rm -f "$state/bootstrap.token"' EXIT
systemctl stop nimbusops-agent.service 2>/dev/null || true
if [[ $reenroll == --reenroll ]]; then
  runuser -u nimbusops-agent -- "$target/venv/bin/python" -m nimbusops_agent --server-url "$server" --hostname "$hostname" --state-file "$state/agent.json" --bootstrap-token-file "$state/bootstrap.token" --telemetry-only --reenroll
else
  if ! runuser -u nimbusops-agent -- "$target/venv/bin/python" -m nimbusops_agent --server-url "$server" --hostname "$hostname" --state-file "$state/agent.json" --bootstrap-token-file "$state/bootstrap.token" --telemetry-only --once; then
    # Identity is atomically saved only after successful registration. A failed
    # first telemetry request must not strand that identity without a service.
    [[ -s $state/agent.json ]] || exit 1
    echo 'Registration saved; service will retry telemetry' >&2
  fi
fi
rm -f "$state/bootstrap.token"
cat > /etc/systemd/system/nimbusops-agent.service <<EOF
[Unit]
Description=NimbusOps telemetry agent
After=network-online.target
Wants=network-online.target
[Service]
User=nimbusops-agent
Group=nimbusops-agent
ExecStart=$target/venv/bin/python -m nimbusops_agent --server-url $server --hostname $hostname --state-file $state/agent.json --telemetry-only
Restart=on-failure
RestartSec=10
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$state
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now nimbusops-agent.service
echo 'Agent started. Verify fresh heartbeat AND telemetry in dashboard; service startup alone is not ONLINE proof.'
