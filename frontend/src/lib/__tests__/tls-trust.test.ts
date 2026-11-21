import { describe, expect, it } from "vitest";
import { verifiedInstallCommand } from "../agentCommands";

describe("explicit CA contract", () => {
  it("passes CA to download and across sudo without inherited environment", () => {
    const command = verifiedInstallCommand("https://example.test", "vm", false, "/etc/nimbusops/ca.pem");
    expect(command).toContain("--cacert '/etc/nimbusops/ca.pem'");
    expect(command).toContain("--ca-bundle '/etc/nimbusops/ca.pem'");
    expect(command).not.toContain("sudo -E");
  });
  it("leaves default trust unchanged", () => {
    const command = verifiedInstallCommand("https://example.test", "vm");
    expect(command).not.toContain("--cacert");
    expect(command).not.toContain("--ca-bundle");
  });
  it.each(["", "relative", "/tmp/ca\n.pem", "/tmp/$(bad)", "/tmp/ca file.pem"])("rejects unsafe CA path %s", (path) => {
    expect(() => verifiedInstallCommand("https://example.test", "vm", false, path)).toThrow("CA");
  });
});
