import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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
