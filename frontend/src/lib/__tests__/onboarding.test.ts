import { describe, expect, it } from "vitest";
import { deriveOnboardingState, findHostByHostname } from "../onboarding";
import { installCommands } from "../agentCommands";

describe("onboarding pure functions", () => {
  it("derives WAITING when token is not consumed, not revoked, and not expired", () => {
    const future = new Date(Date.now() + 60_000).toISOString();
    expect(deriveOnboardingState({ expires_at: future, consumed_at: null, revoked_at: null })).toBe("WAITING");
  });

  it("derives EXPIRED when token is past expiry", () => {
    const past = new Date(Date.now() - 60_000).toISOString();
    expect(deriveOnboardingState({ expires_at: past, consumed_at: null, revoked_at: null })).toBe("EXPIRED");
  });

  it("derives CONSUMED when consumed_at is set even if past expiry", () => {
    const past = new Date(Date.now() - 60_000).toISOString();
    expect(deriveOnboardingState({ expires_at: past, consumed_at: "2026-11-16T12:00:00Z", revoked_at: null })).toBe("CONSUMED");
  });

  it("derives REVOKED when revoked_at is set and not consumed", () => {
    const future = new Date(Date.now() + 60_000).toISOString();
    expect(deriveOnboardingState({ expires_at: future, consumed_at: null, revoked_at: "2026-11-16T12:00:00Z" })).toBe("REVOKED");
  });

  it("matches host by hostname case-insensitively and trimmed", () => {
    const hosts = [
      { id: "h-1", hostname: "Edge-Server-01" },
      { id: "h-2", hostname: "web-prod" },
    ] as any;
    expect(findHostByHostname(hosts, "  edge-server-01  ")?.id).toBe("h-1");
    expect(findHostByHostname(hosts, "nonexistent")).toBeUndefined();
  });
});

describe("agentCommands security invariants", () => {
  const origin = "https://ops.example.internal";
  const cmds = installCommands(origin, "/var/lib/nimbusops-agent", "telemetry-only");

  it("never includes any literal token string or --token flag", () => {
    const combined = `${cmds.promptToFile}\n${cmds.systemdTab}\n${cmds.foregroundTab}`;
    expect(combined).not.toMatch(/--token\b/);
    expect(combined).not.toMatch(/bstrp/i);
    expect(combined).not.toMatch(/agt[-_]/i);
  });

  it("enforces prompt-to-file with 0700 permissions and umask 077", () => {
    expect(cmds.promptToFile).toContain("umask 077");
    expect(cmds.promptToFile).toContain("0700");
    expect(cmds.promptToFile).toContain("read -rsp \"Bootstrap token: \"");
    expect(cmds.promptToFile).toContain("unset t");
  });

  it("specifies environment contracts and file references in systemd snippet", () => {
    expect(cmds.systemdTab).toContain("NIMBUSOPS_SERVER_URL=https://ops.example.internal");
    expect(cmds.systemdTab).toContain("NIMBUSOPS_TOKEN_FILE=/var/lib/nimbusops-agent/bootstrap.token");
    expect(cmds.systemdTab).toContain("NIMBUSOPS_STATE_FILE=/var/lib/nimbusops-agent/agent.json");
    expect(cmds.systemdTab).toContain("NIMBUSOPS_AGENT_MODE=telemetry-only");
  });

  it("foreground command uses --bootstrap-token-file", () => {
    expect(cmds.foregroundTab).toContain("--bootstrap-token-file /var/lib/nimbusops-agent/bootstrap.token");
    expect(cmds.foregroundTab).toContain("--server-url https://ops.example.internal");
  });
});
