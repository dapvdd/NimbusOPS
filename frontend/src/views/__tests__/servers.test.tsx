import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Servers from "../Servers";

vi.mock("../../auth/Session", () => ({
  useAdmin: () => true,
  useSession: () => ({ user: { role: "ADMIN", operator_id: "op-1" } }),
}));

describe("Servers view (fleet + filters + awaiting rows)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders real hosts and filter chips filter correctly", async () => {
    const mockHosts = [
      {
        id: "h-1",
        hostname: "web-prod-01",
        status: "ONLINE",
        is_revoked: false,
        environment: "PUBLIC-CLOUD",
        enrollment_status: "ENROLLED",
        docker_enabled: true,
        latest_metrics: { cpu_percent: 15, memory_used_percent: 45, disk_used_percent: 60 },
      },
      {
        id: "h-2",
        hostname: "db-stage-01",
        status: "STALE",
        is_revoked: false,
        environment: "PRIVATE",
        enrollment_status: "ENROLLED",
        docker_enabled: false,
        latest_metrics: null,
      },
      {
        id: "h-3",
        hostname: "edge-dead-01",
        status: "REVOKED",
        is_revoked: true,
        environment: "PRIVATE",
        enrollment_status: "REVOKED",
        docker_enabled: false,
        latest_metrics: null,
      },
    ];

    const mockTokens = [
      {
        id: "bt-1",
        hostname: "new-edge-box",
        expires_at: new Date(Date.now() + 300_000).toISOString(),
        consumed_at: null,
        revoked_at: null,
      },
    ];

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string) => {
        const url = String(input);
        if (url.endsWith("/hosts")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ hosts: mockHosts, count: 3 }),
          };
        }
        if (url.includes("/operators/bootstrap-tokens")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ tokens: mockTokens, count: 1 }),
          };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      })
    );

    render(
      <MemoryRouter>
        <Servers />
      </MemoryRouter>
    );

    // Initial load: ALL filter includes all hosts + awaiting row
    expect(await screen.findByText("web-prod-01")).toBeInTheDocument();
    expect(screen.getByText("db-stage-01")).toBeInTheDocument();
    expect(screen.getByText("edge-dead-01")).toBeInTheDocument();
    expect(screen.getByText("new-edge-box")).toBeInTheDocument();
    expect(screen.getAllByText(/awaiting enrollment/i).length).toBeGreaterThanOrEqual(1);

    // Revoked host shows Re-enroll action link
    const revokedCard = screen.getByText("edge-dead-01").closest("article");
    expect(revokedCard).toHaveTextContent("Re-enroll");

    // Filter by ONLINE
    fireEvent.click(screen.getByRole("button", { name: "ONLINE" }));
    expect(screen.getByText("web-prod-01")).toBeInTheDocument();
    expect(screen.queryByText("db-stage-01")).not.toBeInTheDocument();
    expect(screen.queryByText("edge-dead-01")).not.toBeInTheDocument();
    expect(screen.queryByText("new-edge-box")).not.toBeInTheDocument();

    // Filter by AWAITING
    fireEvent.click(screen.getByRole("button", { name: "AWAITING" }));
    expect(screen.queryByText("web-prod-01")).not.toBeInTheDocument();
    expect(screen.getByText("new-edge-box")).toBeInTheDocument();

    // Filter by REVOKED
    fireEvent.click(screen.getByRole("button", { name: "REVOKED" }));
    expect(screen.getByText("edge-dead-01")).toBeInTheDocument();
    expect(screen.queryByText("web-prod-01")).not.toBeInTheDocument();

    // Back to ALL, search filter
    fireEvent.click(screen.getByRole("button", { name: "ALL" }));
    const searchInput = screen.getByLabelText(/search servers/i);
    fireEvent.change(searchInput, { target: { value: "prod" } });
    expect(screen.getByText("web-prod-01")).toBeInTheDocument();
    expect(screen.queryByText("db-stage-01")).not.toBeInTheDocument();
    expect(screen.queryByText("new-edge-box")).not.toBeInTheDocument();
  });

  it("displays honest metric dashes when metrics are missing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string) => {
        const url = String(input);
        if (url.endsWith("/hosts")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              hosts: [
                {
                  id: "h-no-metrics",
                  hostname: "headless-node",
                  status: "ONLINE",
                  is_revoked: false,
                  latest_metrics: null,
                },
              ],
              count: 1,
            }),
          };
        }
        return { ok: true, status: 200, json: async () => ({ tokens: [], count: 0 }) };
      })
    );

    render(
      <MemoryRouter>
        <Servers />
      </MemoryRouter>
    );

    expect(await screen.findByText("headless-node")).toBeInTheDocument();
    // Look for metric dashes
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
  });

  it("handles API failure by showing error panel with retry", async () => {
    let shouldFail = true;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string) => {
        const url = String(input);
        if (url.endsWith("/hosts")) {
          if (shouldFail) {
            return {
              ok: false,
              status: 500,
              json: async () => ({
                error: { code: "INTERNAL_ERROR", message: "Server database locked" },
              }),
            };
          }
          return {
            ok: true,
            status: 200,
            json: async () => ({
              hosts: [{ id: "h-recovered", hostname: "recovered-host", status: "ONLINE" }],
              count: 1,
            }),
          };
        }
        return { ok: true, status: 200, json: async () => ({ tokens: [], count: 0 }) };
      })
    );

    render(
      <MemoryRouter>
        <Servers />
      </MemoryRouter>
    );

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/retry/i)).toBeInTheDocument();

    // Now recover and click Retry
    shouldFail = false;
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));

    expect(await screen.findByText("recovered-host")).toBeInTheDocument();
  });

  it("safe unregister dialog revokes host upon typed host id confirmation", async () => {
    let hostRevoked = false;
    let revokeMethod = "";
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string, init?: RequestInit) => {
        const url = String(input);
        // The real contract is DELETE /api/v1/hosts/{id} (revoke-to-tombstone
        // via api.revokeHost); anything else would not revoke anything.
        if (url.endsWith("/hosts/h-123") && init?.method === "DELETE") {
          revokeMethod = "DELETE";
          hostRevoked = true;
          return {
            ok: true,
            status: 200,
            json: async () => ({
              id: "h-123",
              hostname: "box-to-remove",
              enrollment_status: "REVOKED",
              is_revoked: true,
            }),
          };
        }
        if (url.endsWith("/hosts") || url.includes("/hosts?")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              hosts: hostRevoked
                ? [{ id: "h-123", hostname: "box-to-remove", status: "REVOKED", is_revoked: true, enrollment_status: "REVOKED" }]
                : [{ id: "h-123", hostname: "box-to-remove", status: "ONLINE", is_revoked: false, enrollment_status: "ENROLLED" }],
              count: 1,
            }),
          };
        }
        return { ok: true, status: 200, json: async () => ({ tokens: [], count: 0 }) };
      })
    );

    render(
      <MemoryRouter>
        <Servers />
      </MemoryRouter>
    );

    expect(await screen.findByText("box-to-remove")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /unregister box-to-remove/i }));

    expect(screen.getByText(/telemetry and history are retained/i)).toBeInTheDocument();
    const unregisterBtn = screen.getByRole("button", { name: /^unregister$/i });
    expect(unregisterBtn).toBeDisabled();

    // Type the host id to confirm
    const confirmInput = screen.getByLabelText(/type .*host id.* to confirm/i);
    fireEvent.change(confirmInput, { target: { value: "h-123" } });
    expect(unregisterBtn).toBeEnabled();

    fireEvent.click(unregisterBtn);

    // The dialog closes only after the revoke request actually succeeded.
    await waitFor(() => {
      expect(screen.queryByLabelText(/type .*host id.* to confirm/i)).not.toBeInTheDocument();
    });
    expect(revokeMethod).toBe("DELETE");
  });
});
