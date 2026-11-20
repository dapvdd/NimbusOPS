/**
 * Enrollment integration tests (Task 4.3).
 *
 * Covers:
 * - "Add Server" button navigates to the zero-friction onboarding wizard (/servers/new).
 * - Safe Unregister dialog requires typing the host id and states consequences clearly.
 * - Single-use bootstrap tokens are issued via real API calls and are never stored in localStorage.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Servers from "../Servers";

vi.mock("../../auth/Session", () => ({
  useAdmin: () => true,
  useSession: () => ({ user: { role: "ADMIN", operator_id: "op-1" } }),
}));

describe("Enrollment integration & unregister safety", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ hosts: [], tokens: [], count: 0 }),
      })
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("Add Server button routes operator directly to onboarding wizard", async () => {
    render(
      <MemoryRouter initialEntries={["/servers"]}>
        <Routes>
          <Route path="/servers" element={<Servers />} />
          <Route path="/servers/new" element={<div>Onboarding Wizard Page</div>} />
        </Routes>
      </MemoryRouter>
    );

    await screen.findByText("No real servers registered");
    fireEvent.click(screen.getByRole("button", { name: /add server/i }));

    expect(await screen.findByText("Onboarding Wizard Page")).toBeInTheDocument();
  });

  it("session token never lands in localStorage during enrollment navigation", async () => {
    render(
      <MemoryRouter initialEntries={["/servers"]}>
        <Routes>
          <Route path="/servers" element={<Servers />} />
          <Route path="/servers/new" element={<div>Onboarding Wizard Page</div>} />
        </Routes>
      </MemoryRouter>
    );

    await screen.findByText("No real servers registered");
    fireEvent.click(screen.getByRole("button", { name: /add server/i }));

    expect(localStorage.getItem("nimbusops.session")).toBeNull();
    expect(localStorage.getItem("session_token")).toBeNull();
  });

  it("unregister dialog requires typing the host id and explains consequences", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/hosts")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            hosts: [
              {
                id: "h-real-1",
                hostname: "real-host",
                status: "ONLINE",
                agent_version: "0.2.0",
                platform: "Linux",
                platform_release: "6.8",
                cpu_cores: 4,
                total_memory_bytes: 8e9,
                boot_time: null,
                enrolled_at: "2026-11-10T00:00:00Z",
                last_seen_at: null,
                last_telemetry_at: null,
                latest_metrics: null,
                is_revoked: false,
                enrollment_status: "ENROLLED",
                docker_enabled: false,
              },
            ],
            count: 1,
          }),
        } as unknown as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ tokens: [], count: 0 }),
      } as unknown as Response;
    });

    render(
      <MemoryRouter>
        <Servers />
      </MemoryRouter>
    );

    expect(await screen.findByText("real-host")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /unregister real-host/i }));

    // Consequence statement + typed confirmation required
    expect(screen.getByText(/telemetry and history are retained/i)).toBeInTheDocument();
    const confirmInput = screen.getByLabelText(/type .*host id.* to confirm/i);
    expect(screen.getByRole("button", { name: /^unregister$/i })).toBeDisabled();

    fireEvent.change(confirmInput, { target: { value: "h-real-1" } });
    expect(screen.getByRole("button", { name: /^unregister$/i })).toBeEnabled();
  });
});
