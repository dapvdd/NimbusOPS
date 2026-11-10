import { afterEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "../../App";
import { addSimServer } from "../../lib/simRegistry";
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
  addSimServer("sim-node", "SIMULATED-STAGING");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = String(url);
      let body: unknown = { status: "ok", version: "test", server_time: new Date().toISOString(), database: "ok" };
      if (path.endsWith("/hosts")) body = { hosts: [real], count: 1 };
      else if (path.includes("/metrics")) body = { host_id: real.id, points: [], count: 0 };
      else if (path.includes("/hosts/")) body = real;
      return { ok: true, json: async () => body };
    }),
  );
  render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
  const sidebar = await screen.findByRole("navigation", { name: "Primary" });
  expect(within(sidebar).getByText("SIMULATED")).toBeInTheDocument();
  const link = await within(sidebar).findByRole("link", { name: /david-lab/i });
  fireEvent.change(screen.getByLabelText("Search servers"), { target: { value: "david" } });
  expect(within(sidebar).queryByText("sim-node")).not.toBeInTheDocument();
  fireEvent.click(link);
  expect(await screen.findByRole("heading", { name: "david-lab" })).toBeInTheDocument();
});
it("navigates simulation tabs without sending its identity to the API", async () => {
  const host = addSimServer("edge-demo", "SIMULATED-DEV");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: "ok", version: "test", server_time: new Date().toISOString(), hosts: [], applications: [] }) }));
  render(<MemoryRouter initialEntries={[`/servers/${host.id}`]}><App /></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "edge-demo" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Deployments" }));
  expect(screen.getByText("Simulated hosts have no real deployments.")).toBeInTheDocument();
  expect(vi.mocked(fetch).mock.calls.every(([url]) => !String(url).includes(host.id))).toBe(true);
  expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
});
