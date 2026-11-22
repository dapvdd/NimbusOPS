import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import HostDetail from "../HostDetail";
vi.mock('../../auth/Session', () => ({ useAdmin: () => true }));

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function setup(inventoryStatus = 200) {
  const requests: { url: string; init?: RequestInit }[] = [];
  let enabled = false;
  vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
    const url = String(input);
    requests.push({ url, init });
    let status = 200;
    let body: unknown;
    if (url.endsWith("/inventory")) {
      status = inventoryStatus;
      body = status === 200 ? { host_id: "vm-2", observed_at: "2026-11-16T10:00:00Z", received_at: "2026-11-16T10:00:01Z", age_seconds: 25, containers: [{ id: "container-1", names: "owner-nginx", image: "nginx:1.27-alpine", state: "running", managed: false }] } : { error: { code: "INVENTORY_NOT_FOUND", message: "no inventory snapshot" } };
    } else if (url.includes("/metrics")) body = { points: [], count: 0 };
    else {
      if (init?.method === "PATCH") enabled = true;
      body = { id: "vm-2", hostname: "nimbus-syahrul", status: "ONLINE", docker_enabled: enabled, latest_metrics: null };
    }
    return { ok: status === 200, status, json: async () => body };
  }));
  render(<MemoryRouter initialEntries={["/hosts/vm-2"]}><Routes><Route path="/hosts/:hostId" element={<HostDetail />} /></Routes></MemoryRouter>);
  return requests;
}

it("shows only the selected real host's inventory and snapshot age", async () => {
  const requests = setup();
  expect(await screen.findByText("owner-nginx")).toBeInTheDocument();
  expect(screen.getByText(/25 seconds/)).toBeInTheDocument();
  expect(screen.getByText("Unmanaged")).toBeInTheDocument();
  expect(screen.getByRole('link', {name: /Open this host/})).toHaveAttribute('href', '/servers/vm-2?tab=Deployments');
  expect(requests.some(r => r.url.endsWith("/hosts/vm-2/inventory"))).toBe(true);
  expect(requests.every(r => !r.init?.method || r.init.method === "GET")).toBe(true);
});

it("does not equate missing inventory with zero containers", async () => {
  setup(404);
  expect(await screen.findByText(/Docker inventory unavailable/)).toBeInTheDocument();
  expect(screen.queryByText("No containers in this snapshot.")).not.toBeInTheDocument();
  expect(screen.getByText("nimbus-syahrul")).toBeInTheDocument();
});

it("requires explicit owner confirmation before authenticated host-specific enable", async () => {
  const requests = setup();
  const button = await screen.findByRole("button", { name: "Enable Docker for this host" });
  expect(button).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox", { name: /owner explicitly authorized/i }));
  fireEvent.click(button);
  await waitFor(() => expect(requests.some(r => r.init?.method === "PATCH")).toBe(true));
  const patch = requests.find(r => r.init?.method === "PATCH")!;
  expect(patch.url).toMatch(/\/hosts\/vm-2$/);
  expect(JSON.parse(patch.init!.body as string)).toEqual({ docker_enabled: true });
  expect(await screen.findByText("Docker operations enabled")).toBeInTheDocument();
});
