export interface InstallCommands {
  promptToFile: string;
  systemdTab: string;
  foregroundTab: string;
}

/** Immutable demo release; update only together with rebuilt artifact and digest. */
export const AGENT_RELEASE = "nimbusops-agent-1.0.0rc2-dualmode2-ubuntu24.04-amd64.tar.gz";
export const AGENT_SHA256 = "cf2bced62d522473af86dd623458835711957dec25d8ab8c0aac501616a3f2c1";

export function verifiedInstallCommand(origin: string, hostname: string, reenroll = false, caBundle?: string): string {
  if (caBundle !== undefined && (!/^\/[a-zA-Z0-9_./-]+$/.test(caBundle) || caBundle.split("/").includes(".."))) {
    throw new Error("Invalid absolute CA bundle path");
  }
  const quote = (value: string) => "'" + value.replace(/'/g, "'\\''") + "'";
  return `# Ubuntu 24.04 amd64 only. Token is prompted privately by the installer.
# Requires the reviewed release to be published at this exact URL.
(
  set -eu
  work=$(mktemp -d)
  trap 'rm -rf "$work"' EXIT
  curl --fail --silent --show-error --proto '=https' --tlsv1.2${caBundle ? ` --cacert ${quote(caBundle)}` : ""} ${quote(`${origin}/releases/${AGENT_RELEASE}`)} -o "$work/agent.tar.gz"
  printf '%s  %s\\n' '${AGENT_SHA256}' "$work/agent.tar.gz" | sha256sum --check --status
  tar -xzf "$work/agent.tar.gz" -C "$work"
  sudo bash "$work/install.sh" ${quote(origin)} ${quote(hostname)}${reenroll ? " --reenroll" : ""}${caBundle ? ` --ca-bundle ${quote(caBundle)}` : ""}
)`;
}

/**
 * The commands the enrollment wizard shows. They must match the reviewed
 * artifacts that actually ship in this repository (deploy/examples), because
 * an operator will paste them verbatim on a real host:
 *
 * - the agent CLI takes `--telemetry-only` (there is no `--agent-mode` flag);
 * - bootstrap-enroll.sh.example reads NIMBUSOPS_* from its environment and
 *   execs the agent loop, so it is a foreground enrollment, not a service
 *   installer; the values cannot be "sourced" by `sudo` from an env file;
 * - the reviewed unit examples are named nimbusops-agent-telemetry /
 *   -executor; there is no generic `nimbusops-agent` unit.
 */
export function installCommands(
  origin: string,
  stateDir = "/var/lib/nimbusops-agent",
  mode: "telemetry-only" | "executor" = "telemetry-only"
): InstallCommands {
  const promptToFile = `sudo install -d -m 0700 -o nimbusops -g nimbusops ${stateDir}
sudo -u nimbusops bash -c '
  umask 077
  read -rsp "Bootstrap token: " t; echo
  printf "%s" "$t" > "${stateDir}/bootstrap.token"
  unset t
'`;

  const envVars = [
    `NIMBUSOPS_INSTALL_DIR=/opt/nimbusops`,
    `NIMBUSOPS_SERVER_URL=${origin}`,
    `NIMBUSOPS_TOKEN_FILE=${stateDir}/bootstrap.token`,
    `NIMBUSOPS_STATE_FILE=${stateDir}/agent.json`,
    `NIMBUSOPS_AGENT_MODE=${mode}`,
  ].join(" \\\n  ");

  const systemdTab = `# 1. Enroll once, in the foreground, through the reviewed wrapper.
# (It reads NIMBUSOPS_* from its environment — pass them explicitly; an env
# file is NOT inherited by sudo.)
sudo -u nimbusops env \\
  ${envVars} \\
  bash /opt/nimbusops/deploy/examples/bootstrap-enroll.sh.example

# 2. Confirm the host appears here, then Ctrl-C the foreground agent.
# 3. For a persistent service, install ONE reviewed unit example with your
#    substitutions — deploy/examples/systemd/nimbusops-agent-${
      mode === "executor" ? "executor" : "telemetry"
    }.service.example — then:
sudo systemctl daemon-reload
sudo systemctl enable --now <name-of-the-unit-you-installed>`;

  const foregroundTab = `sudo -u nimbusops python -m nimbusops_agent \\
  ${mode === "telemetry-only" ? "--telemetry-only \\\n  " : ""}--server-url ${origin} \\
  --bootstrap-token-file ${stateDir}/bootstrap.token \\
  --state-file ${stateDir}/agent.json`;

  return {
    promptToFile,
    systemdTab,
    foregroundTab,
  };
}
