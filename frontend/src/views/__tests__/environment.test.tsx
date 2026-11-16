import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Servers from "../Servers";

const twoHosts = {
  hosts: [
    { id: "h-1", hostname: "alpha", status: "ONLINE", agent_version: "0.1.0",
      platform: "Linux", platform_release: "x", cpu_cores: 4,
      total_memory_bytes: 8, boot_time: null,
      enrolled_at: "2026-11-12T00:00:00Z", last_seen_at: "2026-11-12T00:00:00Z",
      last_telemetry_at: "2026-11-12T00:00:00Z", latest_metrics: null,
      is_revoked: false, enrollment_status: "ENROLLED", docker_enabled: false,
      environment: "PRIVATE" },
    { id: "h-2", hostname: "beta", status: "OFFLINE", agent_version: "0.1.0",
      platform: "Linux", platform_release: "x", cpu_cores: 2,
      total_memory_bytes: 4, boot_time: null,
      enrolled_at: "2026-11-12T00:00:00Z", last_seen_at: null,
      last_telemetry_at: null, latest_metrics: null,
      is_revoked: false, enrollment_status: "ENROLLED", docker_enabled: false,
      environment: "PUBLIC-CLOUD" },
  ],
  count: 2,
};

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => twoHosts }));
});
afterEach(() => vi.unstubAllGlobals());

it("renders environment chips from real API hosts", async () => {
  render(<MemoryRouter><Servers /></MemoryRouter>);
  await screen.findByText("alpha");
  await screen.findByText("beta");
  // Host chips live in the real-infrastructure article (scoping avoids the
  // filter button labels which use the same words).
  const alphaCard = screen.getByText("alpha").closest("article")!;
  expect(alphaCard.textContent).toContain("PRIVATE");
  const betaCard = screen.getByText("beta").closest("article")!;
  expect(betaCard.textContent).toContain("PUBLIC-CLOUD");
});

it("filters hosts by environment chip", async () => {
  render(<MemoryRouter><Servers /></MemoryRouter>);
  await screen.findByText("alpha");
  fireEvent.click(screen.getByRole("button", { name: /PUBLIC-CLOUD/i }));
  expect(screen.queryByText("alpha")).not.toBeInTheDocument();
  expect(screen.getByText("beta")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /^ALL/i }));
  expect(screen.getByText("alpha")).toBeInTheDocument();
});

// -------------------------------------- S4-3: environment selector (ADMIN)

// The PATCH target is HostDetail (single-host surface); Servers keeps chips
// display-only so a filter-click can never mutate anything.

const detailHost = {
  id: "h-env", hostname: "patchable", status: "ONLINE" as const, agent_version: "0.1.0",
  platform: "Linux", platform_release: "x", cpu_cores: 4,
  total_memory_bytes: 8, boot_time: null,
  enrolled_at: "2026-11-12T00:00:00Z", last_seen_at: "2026-11-12T00:00:00Z",
  last_telemetry_at: "2026-11-12T00:00:00Z", latest_metrics: null,
  is_revoked: false, enrollment_status: "ENROLLED" as const, docker_enabled: false,
  environment: "PRIVATE" as const,
};

function stubDetailApi(patchLog: { url: string; body: unknown }[]) {
  vi.stubGlobal("fetch", vi.fn(async (input: string | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/metrics")) return { ok: true, status: 200, json: async () => ({ points: [], count: 0 }) };
    if (init?.method === "PATCH") {
      patchLog.push({ url, body: JSON.parse(String(init.body)) });
      return { ok: true, status: 200, json: async () => ({ ...detailHost, environment: (JSON.parse(String(init.body)) as { environment: string }).environment }) };
    }
    if (url.includes("/inventory")) return { ok: true, status: 200, json: async () => ({ host_id: "h-env", observed_at: "2026-11-12T00:00:00Z", age_seconds: 1, containers: [] }) };
    return { ok: true, status: 200, json: async () => detailHost };
  }));
}

async function renderDetailAs(role: "ADMIN" | "VIEWER") {
  const Session = await import("../../auth/Session");
  vi.spyOn(Session, "useAdmin").mockReturnValue(role === "ADMIN");
  const { default: HostDetail } = await import("../HostDetail");
  render(
    <MemoryRouter initialEntries={["/hosts/h-env"]}>
      <Routes>
        <Route path="/hosts/:hostId" element={<HostDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

it("ADMIN sees an environment selector and PATCH reaches the API", async () => {
  const patchLog: { url: string; body: unknown }[] = [];
  stubDetailApi(patchLog);
  await renderDetailAs("ADMIN");
  const selector = await screen.findByLabelText("Environment");
  expect(selector).toHaveValue("PRIVATE");
  await act(async () => {
    fireEvent.change(selector, { target: { value: "PUBLIC-CLOUD" } });
  });
  await waitFor(() => expect(patchLog.length).toBe(1));
  expect(patchLog[0].url).toMatch(/\/hosts\/h-env$/);
  expect(patchLog[0].body).toEqual({ environment: "PUBLIC-CLOUD" });
  expect(await screen.findByText("PUBLIC-CLOUD")).toBeInTheDocument();
});

it("PATCH failure surfaces an error and keeps the selector usable", async () => {
  const patchLog: { url: string; body: unknown }[] = [];
  stubDetailApi(patchLog);
  const fetchMock = vi.stubGlobal("fetch", vi.fn(async (input: string | URL, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === "PATCH") return { ok: false, status: 403, json: async () => ({ error: { code: "OPERATOR_FORBIDDEN", message: "no" } }) };
    if (url.includes("/metrics")) return { ok: true, status: 200, json: async () => ({ points: [], count: 0 }) };
    if (url.includes("/inventory")) return { ok: true, status: 200, json: async () => ({ host_id: "h-env", observed_at: "2026-11-12T00:00:00Z", age_seconds: 1, containers: [] }) };
    return { ok: true, status: 200, json: async () => detailHost };
  }));
  void fetchMock;
  await renderDetailAs("ADMIN");
  const selector = await screen.findByLabelText("Environment");
  await act(async () => {
    fireEvent.change(selector, { target: { value: "PUBLIC-CLOUD" } });
  });
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(patchLog.length).toBe(0);
});
