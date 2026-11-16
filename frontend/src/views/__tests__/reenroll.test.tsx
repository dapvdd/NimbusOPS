/**
 * S4-1 (Phase C / Task 4.3): re-enroll navigation UX for revoked hosts.
 *
 * Verifies:
 * - A revoked host card renders a distinct REVOKED chip + "Re-enroll"
 *   action link (ADMIN) on the Servers fleet view directing to /servers/:id.
 * - A healthy host has no re-enroll link (unregister only).
 * - Non-admin users do not see re-enroll or unregister controls.
 * - The client-side sim-* guard remains intact (no sim id ever reaches /hosts).
 */
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Servers from "../Servers";

let mockRole: "ADMIN" | "VIEWER" = "ADMIN";
vi.mock("../../auth/Session", () => ({
  useAdmin: () => mockRole === "ADMIN",
  useSession: () => ({ user: { role: mockRole, operator_id: "op-1" } }),
}));

const revokedHost = {
  id: "h-revoked",
  hostname: "azure-vm",
  status: "OFFLINE",
  agent_version: "0.1.0",
  platform: "Linux",
  platform_release: "7.0.0-1017-azure",
  cpu_cores: 2,
  total_memory_bytes: 8,
  boot_time: null,
  enrolled_at: "2026-11-16T07:49:00Z",
  last_seen_at: "2026-11-16T08:14:00Z",
  last_telemetry_at: "2026-11-16T08:14:00Z",
  latest_metrics: null,
  is_revoked: true,
  enrollment_status: "REVOKED",
  docker_enabled: false,
  environment: "PUBLIC-CLOUD",
};

beforeEach(() => {
  mockRole = "ADMIN";
  localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ hosts: [revokedHost], tokens: [], count: 1 }),
    })
  );
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("revoked host renders a distinct REVOKED chip and re-enroll action link", async () => {
  render(
    <MemoryRouter>
      <Servers />
    </MemoryRouter>
  );
  await screen.findByText("azure-vm");
  const card = screen.getByText("azure-vm").closest("article")!;
  expect(card.textContent).toContain("REVOKED");
  const reenrollLink = screen.getByRole("link", { name: /re-enroll/i });
  expect(reenrollLink).toBeInTheDocument();
  expect(reenrollLink).toHaveAttribute("href", "/servers/h-revoked");
});

it("clicking re-enroll link navigates to host detail page", async () => {
  render(
    <MemoryRouter initialEntries={["/servers"]}>
      <Routes>
        <Route path="/servers" element={<Servers />} />
        <Route path="/servers/:hostId" element={<div>Host Lifecycle Page</div>} />
      </Routes>
    </MemoryRouter>
  );
  await screen.findByText("azure-vm");
  const reenrollLink = screen.getByRole("link", { name: /re-enroll/i });
  fireEvent.click(reenrollLink);
  expect(await screen.findByText("Host Lifecycle Page")).toBeInTheDocument();
});

it("healthy host has no re-enroll action (unregister only)", async () => {
  const healthy = {
    ...revokedHost,
    id: "h-ok",
    hostname: "healthy-vm",
    is_revoked: false,
    enrollment_status: "ENROLLED",
  };
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ hosts: [healthy], tokens: [], count: 1 }),
    })
  );
  render(
    <MemoryRouter>
      <Servers />
    </MemoryRouter>
  );
  await screen.findByText("healthy-vm");
  expect(screen.queryByRole("link", { name: /re-enroll/i })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /unregister/i })).toBeInTheDocument();
});

it("viewer role does not see re-enroll or unregister controls", async () => {
  mockRole = "VIEWER";
  render(
    <MemoryRouter>
      <Servers />
    </MemoryRouter>
  );
  await screen.findByText("azure-vm");
  expect(screen.queryByRole("link", { name: /re-enroll/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /unregister/i })).not.toBeInTheDocument();
});

it("sim-* host ids never reach /hosts/{id}/re-enroll", async () => {
  // The client-side guard rejects sim ids before any fetch is attempted.
  const { api } = await import("../../api/client");
  await expect(api.issueReenrollBootstrap("sim-1234")).rejects.toThrow();
  const calls = vi.mocked(fetch).mock.calls.filter(([u]) => String(u).includes("re-enroll"));
  expect(calls.length).toBe(0);
});
