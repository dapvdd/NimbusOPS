/**
 * Frontend tests use mocked fetch (no backend). They verify rendering,
 * UI states, and honest display of missing/stale/offline data.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Overview from "../Overview";
import HostDetail from "../HostDetail";

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

const hostOnline = {
  id: "h-1",
  hostname: "web-01",
  status: "ONLINE",
  agent_version: "0.1.0",
  platform: "Linux",
  platform_release: "6.8.0",
  cpu_cores: 4,
  total_memory_bytes: 8589934592,
  boot_time: "2026-11-07T10:00:00Z",
  enrolled_at: "2026-11-07T09:00:00Z",
  last_seen_at: "2026-11-08T12:00:00Z",
  last_telemetry_at: "2026-11-08T12:00:00Z",
  latest_metrics: {
    recorded_at: "2026-11-08T12:00:00Z",
    cpu_percent: 23.4,
    memory_used_bytes: 3221225472,
    memory_total_bytes: 8589934592,
    memory_used_percent: 37.5,
    disk_used_bytes: 21474836480,
    disk_total_bytes: 107374182400,
    disk_used_percent: 20.0,
  },
  is_revoked: false,
};

// Keep intervals from leaking.
beforeEach(() => {
  vi.spyOn(window, "setInterval").mockReturnValue(1 as unknown as number);
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("Overview", () => {
  it("renders loading state first", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
    render(
      <MemoryRouter>
        <Overview />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("loading-panel")).toBeInTheDocument();
  });

  it("renders empty state when no hosts", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ hosts: [], count: 0 })));
    render(
      <MemoryRouter>
        <Overview />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId("empty-panel")).toBeInTheDocument());
    expect(screen.getByText(/no hosts registered/i)).toBeInTheDocument();
  });

  it("renders error state on network failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("network down");
      }),
    );
    render(
      <MemoryRouter>
        <Overview />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId("error-panel")).toBeInTheDocument());
    expect(screen.getByText(/api unavailable/i)).toBeInTheDocument();
  });

  it("renders counts and honest telemetry for an online host", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ hosts: [hostOnline], count: 1 })));
    render(
      <MemoryRouter>
        <Overview />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("web-01")).toBeInTheDocument());
    expect(screen.getByTestId("count-registered")).toHaveTextContent("1");
    expect(screen.getByTestId("count-online")).toHaveTextContent("1");
    expect(screen.getByTestId("count-stale")).toHaveTextContent("0");
    // Actual metric values rendered.
    expect(screen.getAllByTestId("metric-value")[0]).toHaveTextContent("23.4%");
  });

  it("shows dashes (not zeros) when a host has no telemetry", async () => {
    const noTele = { ...hostOnline, latest_metrics: null, last_telemetry_at: null, last_seen_at: null };
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ hosts: [noTele], count: 1 })));
    render(
      <MemoryRouter>
        <Overview />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("web-01")).toBeInTheDocument());
    expect(screen.getAllByText("No telemetry received").length).toBe(3);
    expect(screen.getByText(/no telemetry yet/i)).toBeInTheDocument();
  });

  it("marks stale hosts with an explicit warning", async () => {
    const staleHost = { ...hostOnline, status: "STALE" };
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ hosts: [staleHost], count: 1 })));
    render(
      <MemoryRouter>
        <Overview />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText(/telemetry is stale/i)).toBeInTheDocument());
  });

  it("marks offline hosts and never shows them as healthy", async () => {
    const offHost = { ...hostOnline, status: "OFFLINE" };
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ hosts: [offHost], count: 1 })));
    render(
      <MemoryRouter>
        <Overview />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText(/agent offline/i)).toBeInTheDocument());
    expect(screen.getByTestId("count-offline")).toHaveTextContent("1");
    expect(screen.getByTestId("count-online")).toHaveTextContent("0");
  });
});

describe("HostDetail", () => {
  it("renders host identity and metrics from the API", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (String(url).includes("/metrics")) {
        return jsonResponse({
          host_id: "h-1",
          points: [hostOnline.latest_metrics],
          count: 1,
        });
      }
      return jsonResponse(hostOnline);
    }));
    render(
      <MemoryRouter>
        <HostDetail />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole("heading", { name: "web-01" })).toBeInTheDocument());
    expect(screen.getByText(/linux 6\.8\.0/i)).toBeInTheDocument();
    expect(screen.getByText("Reporting")).toBeInTheDocument();
  });

  it("shows never for a host that has not reported", async () => {
    const silent = {
      ...hostOnline,
      status: "OFFLINE",
      last_seen_at: null,
      last_telemetry_at: null,
      latest_metrics: null,
    };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (String(url).includes("/metrics")) return jsonResponse({ host_id: "h-1", points: [], count: 0 });
      return jsonResponse(silent);
    }));
    render(
      <MemoryRouter>
        <HostDetail />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole("heading", { name: "web-01" })).toBeInTheDocument());
    expect(screen.getAllByText("never").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Not reporting")).toBeInTheDocument();
  });

  it("renders not-found for unknown host (404)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ error: { code: "HOST_NOT_FOUND", message: "nope" } }, 404)),
    );
    render(
      <MemoryRouter>
        <HostDetail />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText(/host not found/i)).toBeInTheDocument());
  });
});
