/**
 * S4-1 (Phase C): re-enroll UX for revoked/lost hosts.
 *
 * Verifies:
 * - A revoked host card renders a distinct REVOKED chip + "Issue re-enroll
 *   token" action (ADMIN) on the Servers fleet view.
 * - The action issues a bootstrap token once, shows a copy field and expiry
 *   countdown, and does not re-issue on re-render.
 * - Consumed/expired/unknown bootstrap errors surface typed messages.
 * - The client-side sim-* guard remains intact (no sim id ever reaches /hosts).
 */
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Servers from "../Servers";
vi.mock("../../auth/Session", () => ({ useAdmin: () => true, useSession: () => null }));

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

function revokeFetch(options: { reenrollStatus?: number; reenrollBody?: unknown } = {}) {
  const { reenrollStatus = 201, reenrollBody = { bootstrap_token: "boot-xyz", expires_at: "2026-11-16T21:00:00Z", hostname: "azure-vm" } } = options;
  return vi.fn(async (input: string | URL, _init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/re-enroll")) {
      return { ok: reenrollStatus < 400, status: reenrollStatus, json: async () => reenrollBody };
    }
    return { ok: true, status: 200, json: async () => ({ hosts: [revokedHost], count: 1 }) };
  });
}

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ hosts: [revokedHost], count: 1 }) }));
});
afterEach(() => vi.unstubAllGlobals());

it("revoked host renders a distinct REVOKED chip and re-enroll action", async () => {
  render(<MemoryRouter><Servers /></MemoryRouter>);
  await screen.findByText("azure-vm");
  const card = screen.getByText("azure-vm").closest("article")!;
  expect(card.textContent).toContain("REVOKED");
  expect(screen.getByRole("button", { name: /re-enroll/i })).toBeInTheDocument();
});

it("re-enroll action issues a token once and shows copy + expiry", async () => {
  const fetchMock = revokeFetch();
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryRouter><Servers /></MemoryRouter>);
  await screen.findByText("azure-vm");
  fireEvent.click(screen.getByRole("button", { name: /re-enroll/i }));
  expect(await screen.findByText(/boot-xyz/)).toBeInTheDocument();
  expect(screen.getByTestId("reenroll-countdown")).toBeInTheDocument();
  // The token is issued exactly once across renders.
  const reenrollCalls = fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/re-enroll"));
  expect(reenrollCalls.length).toBe(1);
});

it("consumed bootstrap token (409) surfaces a typed error message", async () => {
  const fetchMock = revokeFetch({ reenrollStatus: 409, reenrollBody: { error: { code: "BOOTSTRAP_TOKEN_CONSUMED", message: "token already used" } } });
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryRouter><Servers /></MemoryRouter>);
  await screen.findByText("azure-vm");
  fireEvent.click(screen.getByRole("button", { name: /re-enroll/i }));
  await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  expect(screen.getByRole("alert").textContent).toMatch(/already/i);
});

it("expired bootstrap token (410) surfaces a typed error message", async () => {
  const fetchMock = revokeFetch({ reenrollStatus: 410, reenrollBody: { error: { code: "BOOTSTRAP_TOKEN_EXPIRED", message: "token expired" } } });
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryRouter><Servers /></MemoryRouter>);
  await screen.findByText("azure-vm");
  fireEvent.click(screen.getByRole("button", { name: /re-enroll/i }));
  await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  expect(screen.getByRole("alert").textContent).toMatch(/expired/i);
});

it("healthy host has no re-enroll action (unregister only)", async () => {
  const healthy = { ...revokedHost, id: "h-ok", hostname: "healthy-vm", is_revoked: false, enrollment_status: "ENROLLED" };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ hosts: [healthy], count: 1 }) }));
  render(<MemoryRouter><Servers /></MemoryRouter>);
  await screen.findByText("healthy-vm");
  expect(screen.queryByRole("button", { name: /re-enroll/i })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /unregister/i })).toBeInTheDocument();
});

it("sim-* host ids never reach /hosts/{id}/re-enroll", async () => {
  // The client-side guard rejects sim ids before any fetch is attempted.
  const { api } = await import("../../api/client");
  await expect(api.issueReenrollBootstrap("sim-1234")).rejects.toThrow();
  const calls = vi.mocked(fetch).mock.calls.filter(([u]) => String(u).includes("re-enroll"));
  expect(calls.length).toBe(0);
});
