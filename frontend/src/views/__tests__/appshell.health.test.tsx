import { afterEach, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppShell } from "../../components/AppShell";

// RC2 F12/F15: the shell must surface dependency degradation honestly and must
// not advertise a stale hardcoded phase label.

const health = (over: Record<string, unknown> = {}) => ({
  status: "ok",
  service: "nimbusops-control-server",
  version: "1.0.0-rc2",
  build: "abc1234",
  server_time: "2026-11-15T10:00:00Z",
  database: "ok",
  ...over,
});

const jsonResponse = (body: unknown) => Promise.resolve({ ok: true, json: async () => body });

/** Route health to the given payload and give other views an empty dataset. */
function stubBackend(healthBody: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: RequestInfo | URL) => {
      const target = String(url);
      if (target.includes("/health")) return jsonResponse(healthBody);
      if (target.includes("/hosts")) return jsonResponse({ hosts: [], count: 0 });
      return jsonResponse({});
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

it("shows a degraded indicator instead of claiming the API is online", async () => {
  stubBackend(health({ status: "degraded", database: "degraded" }));
  render(
    <MemoryRouter>
      <AppShell><p>content</p></AppShell>
    </MemoryRouter>,
  );
  expect(await screen.findByText(/degraded/i)).toBeInTheDocument();
  expect(screen.queryByLabelText("API online")).not.toBeInTheDocument();
});

it("shows the real version and build identity, and no stale phase badge", async () => {
  stubBackend(health());
  render(
    <MemoryRouter>
      <AppShell><p>content</p></AppShell>
    </MemoryRouter>,
  );
  expect(await screen.findByText("v1.0.0-rc2 · abc1234")).toBeInTheDocument();
  expect(screen.queryByText(/Phase 3A/)).not.toBeInTheDocument();
});
