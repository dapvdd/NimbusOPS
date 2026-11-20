import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Host } from "../../api/types";
import HostActions from "../host/HostActions";

let mockRole: "ADMIN" | "VIEWER" = "ADMIN";
vi.mock("../../auth/Session", () => ({
  useAdmin: () => mockRole === "ADMIN",
  useSession: () => ({ user: { role: mockRole, operator_id: "op-1" } }),
}));

describe("HostActions & Credential Lifecycle Dialogs", () => {
  const activeHost: Host = {
    id: "h-active-1",
    hostname: "prod-web-01",
    status: "ONLINE",
    agent_version: "0.2.0",
    platform: "Linux",
    platform_release: "6.8.0",
    cpu_cores: 4,
    total_memory_bytes: 8e9,
    boot_time: null,
    enrolled_at: "2026-11-10T00:00:00Z",
    last_seen_at: "2026-11-16T10:00:00Z",
    last_telemetry_at: "2026-11-16T10:00:00Z",
    latest_metrics: null,
    is_revoked: false,
    enrollment_status: "ENROLLED",
    docker_enabled: true,
    environment: "PUBLIC-CLOUD",
    credential_version: 1,
    credential_grace_until: null,
  };

  const revokedHost: Host = {
    ...activeHost,
    id: "h-revoked-1",
    hostname: "tombstone-01",
    status: "REVOKED",
    is_revoked: true,
    enrollment_status: "REVOKED",
  };

  beforeEach(() => {
    mockRole = "ADMIN";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({}),
      })
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("VIEWER renders nothing (empty DOM)", () => {
    mockRole = "VIEWER";
    const { container } = render(<HostActions host={activeHost} onRefresh={() => {}} />);
    expect(container.firstChild).toBeNull();
    expect(screen.queryByRole("button", { name: /rotate/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /re-enroll/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /revoke/i })).not.toBeInTheDocument();
  });

  it("revoke requires typing the hostname and calls DELETE /hosts/{id}", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/hosts/${activeHost.id}`) && init?.method === "DELETE") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ id: activeHost.id, is_revoked: true }),
        } as Response;
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    const onRefresh = vi.fn();
    render(<HostActions host={activeHost} onRefresh={onRefresh} />);

    fireEvent.click(screen.getByRole("button", { name: /revoke host/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    const confirmBtn = screen.getByRole("button", { name: /confirm revoke/i });
    expect(confirmBtn).toBeDisabled();

    // Type expected hostname
    const input = screen.getByPlaceholderText(activeHost.hostname);
    fireEvent.change(input, { target: { value: activeHost.hostname } });
    expect(confirmBtn).toBeEnabled();

    fireEvent.click(confirmBtn);

    await waitFor(() => {
      const deleteCalls = fetchMock.mock.calls.filter(
        ([url, init]) => String(url).endsWith(`/hosts/${activeHost.id}`) && init?.method === "DELETE"
      );
      expect(deleteCalls.length).toBe(1);
    });
    expect(onRefresh).toHaveBeenCalled();
  });

  it("rotate shows the token once and clears from DOM on close", async () => {
    const secretToken = "super-secret-rotated-token-999";
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/hosts/${activeHost.id}/rotate-credential`) && init?.method === "POST") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            host_id: activeHost.id,
            new_agent_token: secretToken,
            old_token_expires_at: new Date(Date.now() + 3600_000).toISOString(),
          }),
        } as Response;
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<HostActions host={activeHost} onRefresh={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: /rotate credential/i }));

    expect(await screen.findByText(secretToken)).toBeInTheDocument();
    expect(screen.getByTestId("grace-deadline")).toBeInTheDocument();

    // Close the dialog
    fireEvent.click(screen.getByRole("button", { name: /close/i }));

    // Assert the secret token is completely cleared from DOM
    await waitFor(() => {
      expect(screen.queryByText(secretToken)).not.toBeInTheDocument();
    });
  });

  it("re-enroll polls credential_version and is_revoked (not RE_ENROLLED event)", async () => {
    let pollCount = 0;
    const bootstrapToken = "reenroll-bootstrap-token-123";

    const isGet = (init?: RequestInit) => !init || !init.method || init.method === "GET";

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/hosts/${revokedHost.id}/re-enroll`) && init?.method === "POST") {
        return {
          ok: true,
          status: 201,
          json: async () => ({
            bootstrap_token: bootstrapToken,
            expires_at: new Date(Date.now() + 600_000).toISOString(),
            hostname: revokedHost.hostname,
          }),
        } as Response;
      }
      if (url.endsWith(`/hosts/${revokedHost.id}`) && isGet(init)) {
        pollCount++;
        // On 2nd poll, agent has re-enrolled with bumped credential_version and is_revoked: false
        if (pollCount >= 2) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              ...revokedHost,
              credential_version: 2,
              is_revoked: false,
              status: "ONLINE",
              last_seen_at: new Date().toISOString(),
            }),
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          json: async () => revokedHost,
        } as Response;
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<HostActions host={revokedHost} onRefresh={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: /re-enroll/i }));

    expect(await screen.findByText(bootstrapToken)).toBeInTheDocument();

    // Confirm that it detects re-enrollment through credential_version + is_revoked + last_seen_at
    await waitFor(
      () => {
        expect(screen.getByText(/host successfully re-enrolled/i)).toBeInTheDocument();
      },
      { timeout: 5000 }
    );
  });

  it("BOOTSTRAP_TOKEN_ACTIVE error revokes stale token and retries issuance", async () => {
    let reenrollAttempts = 0;
    let tokenRevoked = false;
    const freshToken = "fresh-retry-token-456";

    const isGet = (init?: RequestInit) => !init || !init.method || init.method === "GET";

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/hosts/${revokedHost.id}/re-enroll`) && init?.method === "POST") {
        reenrollAttempts++;
        if (reenrollAttempts === 1) {
          return {
            ok: false,
            status: 409,
            json: async () => ({
              error: {
                code: "BOOTSTRAP_TOKEN_ACTIVE",
                message: "An active bootstrap token already exists for this host",
              },
            }),
          } as Response;
        }
        return {
          ok: true,
          status: 201,
          json: async () => ({
            bootstrap_token: freshToken,
            expires_at: new Date(Date.now() + 600_000).toISOString(),
            hostname: revokedHost.hostname,
          }),
        } as Response;
      }
      if (url.includes("/operators/bootstrap-tokens") && isGet(init)) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            tokens: [
              {
                id: "stale-bt-99",
                hostname: revokedHost.hostname,
                expires_at: new Date(Date.now() + 300_000).toISOString(),
                consumed_at: null,
                revoked_at: null,
              },
            ],
            count: 1,
          }),
        } as Response;
      }
      if (url.includes("/operators/bootstrap-tokens/stale-bt-99") && init?.method === "DELETE") {
        tokenRevoked = true;
        return {
          ok: true,
          status: 200,
          json: async () => ({ id: "stale-bt-99", revoked_at: new Date().toISOString() }),
        } as Response;
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<HostActions host={revokedHost} onRefresh={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: /re-enroll/i }));

    // Should detect BOOTSTRAP_TOKEN_ACTIVE and display the revoke & retry option
    expect(await screen.findByText(/an active token already exists/i)).toBeInTheDocument();
    const revokeRetryBtn = screen.getByRole("button", { name: /revoke existing token & retry/i });

    fireEvent.click(revokeRetryBtn);

    // After clicking, it should call DELETE /operators/bootstrap-tokens/stale-bt-99 and retry re-enroll
    await waitFor(() => {
      expect(tokenRevoked).toBe(true);
      expect(reenrollAttempts).toBe(2);
      expect(screen.getByText(freshToken)).toBeInTheDocument();
    });
  });
});
