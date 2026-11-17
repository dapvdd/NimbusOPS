import { afterEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import App from "../../App";
afterEach(() => { localStorage.clear(); vi.unstubAllGlobals(); });
it("selects a host from the sidebar and navigates to its views", async () => {
  const real = {
    id: "11111111-1111-4111-8111-111111111111",
    hostname: "david-lab",
    status: "ONLINE",
    agent_version: "0.1.0",
    platform: "Linux",
    platform_release: "6.8",
    cpu_cores: 8,
    total_memory_bytes: 17179869184,
    boot_time: null,
    enrolled_at: "2026-11-01T00:00:00Z",
    last_seen_at: new Date().toISOString(),
    last_telemetry_at: new Date().toISOString(),
    latest_metrics: null,
    is_revoked: false,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = String(url);
      let body: unknown = { status: "ok", version: "test", server_time: new Date().toISOString(), database: "ok" };
      if (path.endsWith("/hosts")) body = { hosts: [real], count: 1 };
      else if (path.includes("/metrics")) body = { host_id: real.id, points: [], count: 0 };
      else if (path.includes("/events")) body = { events: [], count: 0 };
      else if (path.includes("/hosts/")) body = real;
      return { ok: true, json: async () => body };
    }),
  );
  render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
  const sidebar = await screen.findByRole("navigation", { name: "Primary" });
  expect(await within(sidebar).findByText("REAL")).toBeInTheDocument();
  const link = await within(sidebar).findByRole("link", { name: /david-lab/i });
  fireEvent.change(screen.getByLabelText("Search servers"), { target: { value: "david" } });
  fireEvent.click(link);
  expect(await screen.findByRole("heading", { name: "david-lab" })).toBeInTheDocument();
});
it("refuses a simulated id and never queries the API with it", async () => {
  const simulatedId = "sim-00000000-0000-4000-8000-000000000000";
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ status: "ok", version: "test", server_time: new Date().toISOString(), hosts: [], applications: [] }),
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryRouter initialEntries={[`/servers/${simulatedId}`]}><App /></MemoryRouter>);
  // The real-host view refuses simulated identities instead of inventing one.
  expect(await screen.findByTestId("error-panel")).toBeInTheDocument();
  expect(screen.getByText(/simulated resources cannot access real infrastructure endpoints/i)).toBeInTheDocument();
  expect(fetchMock.mock.calls.every(([url]) => !String(url).includes(simulatedId))).toBe(true);
  expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
});
it("shows different content for Monitoring and Overview on a real host", async () => {
  const real = {
    id: "22222222-2222-4222-8222-222222222222",
    hostname: "monitor-me",
    status: "ONLINE",
    agent_version: "0.1.0",
    platform: "Linux",
    platform_release: "6.8",
    cpu_cores: 8,
    total_memory_bytes: 17179869184,
    boot_time: null,
    enrolled_at: "2026-11-01T00:00:00Z",
    last_seen_at: new Date().toISOString(),
    last_telemetry_at: new Date().toISOString(),
    latest_metrics: null,
    is_revoked: false,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = String(url);
      let body: unknown = { status: "ok", version: "test", server_time: new Date().toISOString(), database: "ok" };
      if (path.endsWith("/hosts")) body = { hosts: [real], count: 1 };
      else if (path.includes("/metrics")) body = { host_id: real.id, points: [], count: 0 };
      else if (path.includes("/events")) body = { events: [], count: 0 };
      else if (path.includes("/hosts/")) body = real;
      return { ok: true, json: async () => body };
    }),
  );
  render(<MemoryRouter initialEntries={[`/servers/${real.id}?tab=Monitoring`]}><App /></MemoryRouter>);
  expect(await screen.findByText("Recent telemetry")).toBeInTheDocument();
  expect(screen.queryByText("Enrolled at")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Overview" }));
  expect(await screen.findByText("Enrolled at")).toBeInTheDocument();
});
it("redirects the legacy /hosts/:hostId route to /servers/:hostId", async () => {
  const legacy = {
    id: "legacy-id",
    hostname: "legacy-host",
    status: "ONLINE",
    agent_version: "0.1.0",
    platform: "Linux",
    platform_release: "6.8",
    cpu_cores: 4,
    total_memory_bytes: 8589934592,
    boot_time: null,
    enrolled_at: "2026-11-01T00:00:00Z",
    last_seen_at: new Date().toISOString(),
    last_telemetry_at: new Date().toISOString(),
    latest_metrics: null,
    is_revoked: false,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = String(url);
      if (path.includes("/operators/me")) {
        return { ok: true, json: async () => ({ operator_id: "op-1", username: "admin", role: "ADMIN" }) };
      }
      if (path.includes("/operators/session/csrf")) return { ok: true, json: async () => ({ csrf_token: "csrf-1" }) };
      if (path.endsWith("/hosts")) return { ok: true, json: async () => ({ hosts: [legacy], count: 1 }) };
      if (path.includes("/events")) return { ok: true, json: async () => ({ events: [], count: 0 }) };
      if (path.includes("/metrics")) return { ok: true, json: async () => ({ host_id: legacy.id, points: [], count: 0 }) };
      return { ok: true, json: async () => legacy };
    }),
  );
  function LocationProbe() {
    const location = useLocation();
    return <div data-testid="location">{location.pathname}</div>;
  }
  render(
    <MemoryRouter initialEntries={["/hosts/legacy-id"]}>
      <LocationProbe />
      <App />
    </MemoryRouter>,
  );
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/servers/legacy-id"));
});
