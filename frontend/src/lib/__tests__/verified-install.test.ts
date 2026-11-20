import { describe, expect, it } from "vitest";
import { verifiedInstallCommand } from "../agentCommands";

describe("verified installer", () => {
  it("pins bytes and passes exact FQDN without embedding credentials", () => {
    const command = verifiedInstallCommand("https://demo.example.org", "ubuntu.example.org");
    expect(command).toContain("sha256sum --check --status");
    expect(command).toContain("8f0a715761aff04920201409c95d648450329d68acb1e41a616c5e131637d7d9");
    expect(command.indexOf("sha256sum")).toBeLessThan(command.indexOf("tar -xzf"));
    expect(command).toContain("'ubuntu.example.org'");
    expect(command).not.toContain("/opt/nimbusops/");
    expect(command).not.toContain("bootstrap-token");
  });
  it("quotes shell metacharacters rather than executing them", () => {
    expect(verifiedInstallCommand("https://demo.example.org", "x'; touch /tmp/bad; '")).toContain("'\\''");
  });
  it("requires explicit reenroll flag", () => {
    expect(verifiedInstallCommand("https://demo.example.org", "demo.example.org", true)).toContain("--reenroll");
    expect(verifiedInstallCommand("https://demo.example.org", "demo.example.org")).not.toContain("--reenroll");
  });
});
