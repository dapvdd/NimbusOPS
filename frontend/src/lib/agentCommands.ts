export interface InstallCommands {
  promptToFile: string;
  systemdTab: string;
  foregroundTab: string;
}

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

  const systemdTab = `# 1. Configure agent environment:
# /etc/nimbusops/agent.env
NIMBUSOPS_INSTALL_DIR=/opt/nimbusops/agent
NIMBUSOPS_SERVER_URL=${origin}
NIMBUSOPS_TOKEN_FILE=${stateDir}/bootstrap.token
NIMBUSOPS_STATE_FILE=${stateDir}/agent.json
NIMBUSOPS_AGENT_MODE=${mode}

# 2. Complete bootstrap enrollment and start the service:
sudo -u nimbusops bash /opt/nimbusops/deploy/examples/bootstrap-enroll.sh.example
sudo systemctl enable --now nimbusops-agent`;

  const foregroundTab = `sudo -u nimbusops python -m nimbusops_agent \\
  --bootstrap-token-file ${stateDir}/bootstrap.token \\
  --server-url ${origin} \\
  --state-file ${stateDir}/agent.json \\
  --agent-mode ${mode}`;

  return {
    promptToFile,
    systemdTab,
    foregroundTab,
  };
}
