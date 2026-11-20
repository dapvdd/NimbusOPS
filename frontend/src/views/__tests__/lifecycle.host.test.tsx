/**
 * S4-1b (Phase C): HostDetail rotate-credential + re-enroll actions.
 *
 * Verifies (ADMIN):
 * - Rotate button calls POST /hosts/{id}/rotate-credential and shows the new
 *   token once with the grace deadline.
 * - Re-enroll button calls POST /hosts/{id}/re-enroll and shows the bootstrap
 *   token once.
 * VIEWER: neither control renders.
 */
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const healthyHost = {
  id: "h-rot",
  hostname: "rotate-me",
  status: "ONLINE" as const,
  agent_version: "0.1.0",
  platform: "Linux",
  platform_release: "6.8.0-45-generic",
  cpu_cores: 4,
  total_memory_bytes: 8,
  boot_time: null,
  enrolled_at: "2026-11-16T07:49:00Z",
  last_seen_at: "2026-11-16T08:14:00Z",
  last_telemetry_at: "2026-11-16T08:14:00Z",
  latest_metrics: null,
  is_revoked: false,
  enrollment_status: "ENROLLED" as const,
  docker_enabled: false,
  environment: "PRIVATE" as const,
};

function stubLifecycleApi(log: { url: string; body: unknown }[], host = healthyHost) {
  vi.stubGlobal("fetch", vi.fn(async (input: string | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/metrics")) return { ok: true, status: 200, json: async () => ({ points: [], count: 0 }) };
    if (url.includes("/inventory")) return { ok: true, status: 200, json: async () => ({ host_id: host.id, observed_at: "2026-11-16T08:00:00Z", age_seconds: 1, containers: [] }) };
    if (url.endsWith("/rotate-credential")) {
      log.push({ url, body: JSON.parse(String(init?.body)) });
      return { ok: true, status: 200, json: async () => ({ host_id: host.id, new_agent_token: "new-agent-tok", old_token_expires_at: "2026-11-16T09:00:00Z" }) };
    }
    if (url.endsWith("/re-enroll")) {
      log.push({ url, body: JSON.parse(String(init?.body)) });
      return { ok: true, status: 201, json: async () => ({ bootstrap_token: "boot-once", expires_at: "2026-11-16T09:00:00Z", hostname: host.hostname }) };
    }
    return { ok: true, status: 200, json: async () => host };
  }));
}

async function renderDetailAs(role: "ADMIN" | "VIEWER") {
  const Session = await import("../../auth/Session");
  vi.spyOn(Session, "useAdmin").mockReturnValue(role === "ADMIN");
  const { default: HostDetail } = await import("../HostDetail");
  render(
    <MemoryRouter initialEntries={["/hosts/h-rot"]}>
      <Routes>
        <Route path="/hosts/:hostId" element={<HostDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("ADMIN can rotate the credential; token shown once with grace deadline", async () => {
  const log: { url: string; body: unknown }[] = [];
  stubLifecycleApi(log);
  await renderDetailAs("ADMIN");
  fireEvent.click(await screen.findByRole("button", { name: /rotate credential/i }));
  expect(await screen.findByText(/new-agent-tok/)).toBeInTheDocument();
  await waitFor(() => expect(log.length).toBe(1));
  expect(log[0].url).toMatch(/\/hosts\/h-rot\/rotate-credential$/);
  expect(screen.getByTestId("grace-deadline").textContent).toMatch(/grace/i);
});

it("ADMIN can re-enroll from the host detail; token shown once", async () => {
  const log: { url: string; body: unknown }[] = [];
  stubLifecycleApi(log);
  await renderDetailAs("ADMIN");
  fireEvent.click(await screen.findByRole("button", { name: /re-enroll/i }));
  expect(await screen.findByText(/boot-once/)).toBeInTheDocument();
  await waitFor(() => expect(log.length).toBe(1));
  expect(log[0].url).toMatch(/\/hosts\/h-rot\/re-enroll$/);
});

it("VIEWER sees neither rotate nor re-enroll controls", async () => {
  stubLifecycleApi([]);
  await renderDetailAs("VIEWER");
  await screen.findByText("rotate-me");
  expect(screen.queryByRole("button", { name: /rotate credential/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /re-enroll/i })).not.toBeInTheDocument();
});

it("rotate failure surfaces an error, not a silent no-op", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: string | URL, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === "POST" && url.endsWith("/rotate-credential")) return { ok: false, status: 409, json: async () => ({ error: { code: "HOST_REVOKED", message: "revoked" } }) };
    if (url.includes("/metrics")) return { ok: true, status: 200, json: async () => ({ points: [], count: 0 }) };
    if (url.includes("/inventory")) return { ok: true, status: 200, json: async () => ({ host_id: "h-rot", observed_at: "2026-11-16T08:00:00Z", age_seconds: 1, containers: [] }) };
    return { ok: true, status: 200, json: async () => healthyHost };
  }));
  await renderDetailAs("ADMIN");
  fireEvent.click(await screen.findByRole("button", { name: /rotate credential/i }));
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});
