import { describe, expect, it } from "vitest";
import { ApiFailure } from "../../api/client";
import { guidanceFor } from "../errorGuidance";

describe("errorGuidance", () => {
  it("maps HOST_REVOKED to re-enroll guidance", () => {
    const err = new ApiFailure("http", "Host revoked", 401, "HOST_REVOKED");
    const g = guidanceFor(err);
    expect(g.title).toMatch(/revoked/i);
    expect(g.detail).toContain("credential is revoked");
    expect(g.action?.kind).toBe("reenroll");
  });

  it("maps HOST_NOT_FOUND to fleet return action", () => {
    const err = new ApiFailure("http", "Not found", 404, "HOST_NOT_FOUND");
    const g = guidanceFor(err);
    expect(g.detail).toContain("no longer exists");
    expect(g.action?.to).toBe("/servers");
    expect(g.action?.kind).toBe("fleet");
  });

  it("maps bootstrap token issues to reissue action", () => {
    for (const code of ["BOOTSTRAP_TOKEN_EXPIRED", "BOOTSTRAP_TOKEN_CONSUMED", "BOOTSTRAP_TOKEN_INVALID"]) {
      const err = new ApiFailure("http", "Token error", 400, code);
      const g = guidanceFor(err);
      expect(g.detail).toContain("no longer usable");
      expect(g.action?.kind).toBe("reissue");
    }
  });

  it("maps BOOTSTRAP_TOKEN_ACTIVE to revoke and reissue", () => {
    const err = new ApiFailure("http", "Token active", 409, "BOOTSTRAP_TOKEN_ACTIVE");
    const g = guidanceFor(err);
    expect(g.detail).toContain("still active");
    expect(g.action?.kind).toBe("reissue");
  });

  it("maps BOOTSTRAP_TOKEN_HOSTNAME_MISMATCH to hostname mismatch guidance", () => {
    const err = new ApiFailure("http", "Mismatch", 401, "BOOTSTRAP_TOKEN_HOSTNAME_MISMATCH");
    const g = guidanceFor(err);
    expect(g.detail).toContain("different hostname");
  });

  it("maps HOSTNAME_TAKEN to already enrolled guidance", () => {
    const err = new ApiFailure("http", "Taken", 409, "HOSTNAME_TAKEN");
    const g = guidanceFor(err);
    expect(g.detail).toContain("already enrolled");
    expect(g.action?.kind).toBe("reenroll");
  });

  it("maps OPERATOR_AUTH_REQUIRED to sign in", () => {
    const err = new ApiFailure("http", "Auth required", 401, "OPERATOR_AUTH_REQUIRED");
    const g = guidanceFor(err);
    expect(g.detail).toContain("session expired");
    expect(g.action?.kind).toBe("fleet");
  });

  it("maps OPERATOR_FORBIDDEN to role warning with no retry", () => {
    const err = new ApiFailure("http", "Forbidden", 403, "OPERATOR_FORBIDDEN");
    const g = guidanceFor(err);
    expect(g.detail).toContain("role cannot perform");
    expect(g.action).toBeUndefined();
  });

  it("maps DOCKER_NOT_AUTHORIZED to docker execution guidance", () => {
    const err = new ApiFailure("http", "Docker not enabled", 403, "DOCKER_NOT_AUTHORIZED");
    const g = guidanceFor(err);
    expect(g.detail).toContain("Docker execution is disabled");
    expect(g.surface).toBe("operation");
  });

  it("maps AGENT_UNREACHABLE and TIMEOUT to retry", () => {
    for (const code of ["AGENT_UNREACHABLE", "TIMEOUT"]) {
      const err = new ApiFailure("http", "Agent timeout", 504, code);
      const g = guidanceFor(err);
      expect(g.detail).toContain("did not respond in time");
      expect(g.action?.kind).toBe("refetch");
    }
  });

  it("maps network failure to API connectivity guidance", () => {
    const err = new ApiFailure("network", "Cannot reach the NimbusOps server.");
    const g = guidanceFor(err);
    expect(g.detail).toContain("Cannot reach the API");
    expect(g.action?.kind).toBe("refetch");
  });

  it("handles unknown codes gracefully with safe fallback", () => {
    const err = new ApiFailure("http", "Something went wrong on the server", 500, "CUSTOM_ERR_99");
    const g = guidanceFor(err);
    expect(g.title).toBe("Operation failed");
    expect(g.code).toBe("CUSTOM_ERR_99");
    expect(g.detail).toBe("Something went wrong on the server");
  });

  it("never leaks secret token patterns in message details", () => {
    const err = new ApiFailure("http", "Token bstrp_abcdef1234567890 failed validation", 400);
    const g = guidanceFor(err);
    expect(g.detail).not.toContain("bstrp_abcdef1234567890");
  });
});
