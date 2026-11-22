/**
 * Frontend tests use mocked fetch (no backend). They verify rendering,
 * UI states, and honest display of missing/stale/offline data.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Overview from "../Overview";
import HostDetail from "../HostDetail";
import { StatusBadge } from "../../components/StatusBadge";

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

// Keep intervals from leaking. Every registered poll callback is captured so
// tests can drive a refresh manually (the interval never fires under the mock).
const pollHandlers: Array<() => void> = [];
beforeEach(() => {
  vi.spyOn(window, "setInterval").mockImplementation(((handler: TimerHandler) => {
    pollHandlers.push(handler as () => void);
    return pollHandlers.length as unknown as number;
  }) as typeof window.setInterval);
});
afterEach(() => {
  pollHandlers.length = 0;
  vi.restoreAllMocks();
});

describe("Overview", () => {
  it("does not claim all clear after a fleet refresh fails", async () => {
    let fail = false;
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).endsWith('/hosts')) {
        if (fail) throw new Error('offline');
        return jsonResponse({hosts: [hostOnline], count: 1});
      }
      if (String(url).includes('/bootstrap-tokens')) return jsonResponse({tokens: []});
      if (String(url).includes('/operations')) return jsonResponse({operations: []});
      return jsonResponse({status: 'ok', database: 'ok'});
    }));
    render(<MemoryRouter><Overview /></MemoryRouter>);
    await screen.findByTestId('all-clear');
    expect(screen.getByTestId('all-clear')).toHaveTextContent('Provisioning outcomes are separate');
    fail = true;
    await act(async () => { pollHandlers.forEach(fn => fn()); });
    await screen.findAllByText(/Last refresh failed/);
    expect(screen.queryByTestId('all-clear')).not.toBeInTheDocument();
  });
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

describe("Overview dashboard", () => {
  const revoked = {
    ...hostOnline,
    id: "h-rev",
    hostname: "revoked-vm",
    status: "REVOKED",
    is_revoked: true,
    enrollment_status: "REVOKED",
  };

  function routeFetch(opts: {
    hosts?: unknown[];
    tokens?: unknown[];
    operations?: unknown[];
    health?: Record<string, unknown>;
  }) {
    return vi.fn(async (url: string) => {
      const path = String(url);
      if (path.includes("/operators/bootstrap-tokens")) {
        return jsonResponse({ tokens: opts.tokens ?? [], count: (opts.tokens ?? []).length });
      }
      if (path.includes("/operations")) {
        return jsonResponse({ operations: opts.operations ?? [], count: (opts.operations ?? []).length, total: 0, offset: 0 });
      }
      if (path.includes("/health")) {
        return jsonResponse(opts.health ?? { status: "ok", service: "nimbusops", version: "1", build: "b", server_time: new Date().toISOString(), database: "ok" });
      }
      return jsonResponse({ hosts: opts.hosts ?? [], count: (opts.hosts ?? []).length });
    });
  }

  it("puts a revoked host in Needs attention and never counts it as online", async () => {
    vi.stubGlobal("fetch", routeFetch({ hosts: [hostOnline, revoked] }));
    render(<MemoryRouter><Overview /></MemoryRouter>);
    await waitFor(() => expect(screen.getByTestId("needs-attention")).toBeInTheDocument());
    expect(screen.getByTestId("count-online")).toHaveTextContent("1");
    expect(screen.getByTestId("count-revoked")).toHaveTextContent("1");
    expect(screen.getByTestId("needs-attention")).toHaveTextContent(/revoked-vm/i);
  });

  it("links each attention entry to its resolving action", async () => {
    vi.stubGlobal("fetch", routeFetch({ hosts: [revoked] }));
    render(<MemoryRouter><Overview /></MemoryRouter>);
    await waitFor(() => expect(screen.getByTestId("needs-attention")).toBeInTheDocument());
    const link = screen.getByTestId("needs-attention").querySelector("a")!;
    expect(link).toHaveAttribute("href", "/servers/h-rev");
  });

  it("renders real recent operations with status and error code", async () => {
    vi.stubGlobal("fetch", routeFetch({
      hosts: [hostOnline],
      operations: [
        { id: "op-1", deployment_id: "d-1", host_id: "h-1", op_type: "DEPLOY", status: "FAILED", created_at: "2026-11-16T10:00:00Z", updated_at: "2026-11-16T10:01:00Z", completed_at: null, result: null, error_code: "CONTAINER_FAILED", error_message: "boom" },
      ],
    }));
    render(<MemoryRouter><Overview /></MemoryRouter>);
    await waitFor(() => expect(screen.getByTestId("recent-operations")).toBeInTheDocument());
    const ops = screen.getByTestId("recent-operations");
    expect(ops).toHaveTextContent("DEPLOY");
    expect(ops).toHaveTextContent("FAILED");
    expect(ops).toHaveTextContent("CONTAINER_FAILED");
    expect(ops.querySelector('a[href="/activity"]')).not.toBeNull();
  });

  it("shows no all-clear banner while something needs attention", async () => {
    vi.stubGlobal("fetch", routeFetch({ hosts: [revoked] }));
    render(<MemoryRouter><Overview /></MemoryRouter>);
    await waitFor(() => expect(screen.getByTestId("needs-attention")).toBeInTheDocument());
    expect(screen.queryByTestId("all-clear")).not.toBeInTheDocument();
  });

  it("shows the all-clear banner only when health is ok and nothing needs attention", async () => {
    vi.stubGlobal("fetch", routeFetch({ hosts: [hostOnline] }));
    render(<MemoryRouter><Overview /></MemoryRouter>);
    await waitFor(() => expect(screen.getByTestId("all-clear")).toBeInTheDocument());
  });

  it("counts live awaiting-enrollment tokens and flags ones expiring soon", async () => {
    const soon = new Date(Date.now() + 60_000).toISOString();
    vi.stubGlobal("fetch", routeFetch({
      hosts: [hostOnline],
      tokens: [{ id: "bt-1", hostname: "pending-vm", created_at: new Date().toISOString(), expires_at: soon, consumed_at: null, consumed_by_host_id: null, revoked_at: null }],
    }));
    render(<MemoryRouter><Overview /></MemoryRouter>);
    await waitFor(() => expect(screen.getByTestId("count-awaiting")).toHaveTextContent("1"));
    expect(screen.getByTestId("needs-attention")).toHaveTextContent(/pending-vm/i);
    expect(screen.getByTestId("needs-attention")).toHaveTextContent(/expir/i);
  });

  it("shows the awaiting count as unknown, never zero, when the token list cannot be read", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const path = String(url);
      if (path.includes("/operators/bootstrap-tokens")) {
        // ADMIN-only endpoint behind a VIEWER session.
        return jsonResponse({ error: { code: "OPERATOR_FORBIDDEN", message: "ADMIN role required" } }, 403);
      }
      if (path.includes("/operations")) {
        return jsonResponse({ operations: [], count: 0, total: 0, offset: 0 });
      }
      if (path.includes("/health")) {
        return jsonResponse({ status: "ok", service: "nimbusops", version: "1", build: "b", server_time: new Date().toISOString(), database: "ok" });
      }
      return jsonResponse({ hosts: [hostOnline], count: 1 });
    }));
    render(<MemoryRouter><Overview /></MemoryRouter>);
    await waitFor(() => expect(screen.getByTestId("count-awaiting")).toHaveTextContent("—"));
    expect(screen.getByTestId("count-awaiting")).not.toHaveTextContent("0");
    // And the page says why instead of implying an empty enrollment queue.
    expect(screen.getByTestId("count-awaiting")).toHaveAccessibleDescription(/unavailable/i);
  });

  it("marks the data as from the previous poll when a refresh fails after success", async () => {
    let fail = false;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (fail) {
        // Host reads fail; everything else succeeds. The page keeps the last
        // good fleet and must label it as such.
        if (String(url).includes("/hosts")) throw new TypeError("network down");
        const p = String(url);
        if (p.includes("/operators/bootstrap-tokens")) return jsonResponse({ tokens: [], count: 0 });
        if (p.includes("/operations")) return jsonResponse({ operations: [], count: 0, total: 0, offset: 0 });
        if (p.includes("/health")) {
          return jsonResponse({ status: "ok", service: "nimbusops", version: "1", build: "b", server_time: new Date().toISOString(), database: "ok" });
        }
      }
      const path = String(url);
      if (path.includes("/operators/bootstrap-tokens")) return jsonResponse({ tokens: [], count: 0 });
      if (path.includes("/operations")) return jsonResponse({ operations: [], count: 0, total: 0, offset: 0 });
      if (path.includes("/health")) {
        return jsonResponse({ status: "ok", service: "nimbusops", version: "1", build: "b", server_time: new Date().toISOString(), database: "ok" });
      }
      return jsonResponse({ hosts: [hostOnline], count: 1 });
    }));
    render(<MemoryRouter><Overview /></MemoryRouter>);
    await waitFor(() => expect(screen.getByTestId("refresh-status")).toBeInTheDocument());
    fail = true;
    // The suite mocks window.setInterval (no automatic 30s poll), so drive the
    // page's own registered poll callback once with the host feed failing.
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const callsBefore = fetchMock.mock.calls.length;
    // The suite mocks window.setInterval (no automatic 30s poll), so drive the
    // page's own registered poll callback once with the host feed failing.
    // testing-library registers its own timer bookkeeping handler, so run the
    // captured handlers until one of them issues new fetches.
    await act(async () => {
      const before = fetchMock.mock.calls.length;
      for (const handler of pollHandlers) {
        handler();
        await Promise.resolve();
        await Promise.resolve();
        if (fetchMock.mock.calls.length > before) break;
      }
    });
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(callsBefore));
    await waitFor(() =>
      expect(screen.getByTestId("refresh-status")).toHaveTextContent(/last refresh failed/i),
    );
    // The previously loaded fleet is still shown, clearly stale.
    expect(screen.getByTestId("fleet-table")).toBeInTheDocument();
  });

  it("flags docker_enabled hosts whose agent reports telemetry-only mode", async () => {
    const misconfigured = { ...hostOnline, docker_enabled: true, agent_mode: "telemetry-only" as const };
    vi.stubGlobal("fetch", routeFetch({ hosts: [misconfigured] }));
    render(<MemoryRouter><Overview /></MemoryRouter>);
    await waitFor(() => expect(screen.getByTestId("needs-attention")).toBeInTheDocument());
    expect(screen.getByTestId("needs-attention")).toHaveTextContent(/docker/i);
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

  it("renders StatusBadge with REVOKED status and unknown fallback safely", () => {
    const { container: c1 } = render(<StatusBadge status={"REVOKED" as any} />);
    expect(c1).toBeInTheDocument();
    expect(screen.getByText("Revoked")).toBeInTheDocument();

    const { container: c2 } = render(<StatusBadge status={"UNKNOWN_VAL" as any} />);
    expect(c2).toBeInTheDocument();
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });

  it("revoked host shows 'Credential revoked — re-enroll required'", async () => {
    const revokedHost = {
      ...hostOnline,
      status: "REVOKED",
      is_revoked: true,
      enrollment_status: "REVOKED",
    };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (String(url).includes("/metrics")) return jsonResponse({ host_id: "h-1", points: [], count: 0 });
      if (String(url).includes("/events")) return jsonResponse({ events: [], count: 0 });
      return jsonResponse(revokedHost);
    }));
    render(
      <MemoryRouter>
        <HostDetail />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole("heading", { name: "web-01" })).toBeInTheDocument());
    expect(screen.getByText("Credential revoked — re-enroll required")).toBeInTheDocument();
  });

  it("agent_mode=null renders 'not reported'", async () => {
    const hostNoMode = {
      ...hostOnline,
      agent_mode: null,
    };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (String(url).includes("/metrics")) return jsonResponse({ host_id: "h-1", points: [], count: 0 });
      if (String(url).includes("/events")) return jsonResponse({ events: [], count: 0 });
      return jsonResponse(hostNoMode);
    }));
    render(
      <MemoryRouter>
        <HostDetail />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole("heading", { name: "web-01" })).toBeInTheDocument());
    expect(screen.getByText("not reported")).toBeInTheDocument();
  });

  it("grace countdown renders only when credential_grace_until is non-null", async () => {
    const hostWithGrace = {
      ...hostOnline,
      credential_grace_until: "2026-11-20T12:00:00Z",
    };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (String(url).includes("/metrics")) return jsonResponse({ host_id: "h-1", points: [], count: 0 });
      if (String(url).includes("/events")) return jsonResponse({ events: [], count: 0 });
      return jsonResponse(hostWithGrace);
    }));
    const { unmount } = render(
      <MemoryRouter>
        <HostDetail />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole("heading", { name: "web-01" })).toBeInTheDocument());
    expect(screen.getByTestId("runtime-grace-deadline")).toBeInTheDocument();
    unmount();

    // Now with null grace
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (String(url).includes("/metrics")) return jsonResponse({ host_id: "h-1", points: [], count: 0 });
      if (String(url).includes("/events")) return jsonResponse({ events: [], count: 0 });
      return jsonResponse({ ...hostOnline, credential_grace_until: null });
    }));
    render(
      <MemoryRouter>
        <HostDetail />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole("heading", { name: "web-01" })).toBeInTheDocument());
    expect(screen.queryByTestId("runtime-grace-deadline")).not.toBeInTheDocument();
  });

  it("events render newest-first with the mocked API", async () => {
    const mockEvents = [
      { id: 2, host_id: "h-1", event: "ROTATE_CREDENTIAL", actor: "admin", detail: null, at: "2026-11-16T12:00:00Z", created_at: "2026-11-16T12:00:00Z" },
      { id: 1, host_id: "h-1", event: "ENROLLED", actor: "system", detail: null, at: "2026-11-16T10:00:00Z", created_at: "2026-11-16T10:00:00Z" },
    ];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (String(url).includes("/metrics")) return jsonResponse({ host_id: "h-1", points: [], count: 0 });
      if (String(url).includes("/events")) return jsonResponse({ events: mockEvents, count: 2 });
      return jsonResponse(hostOnline);
    }));
    render(
      <MemoryRouter>
        <HostDetail />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole("heading", { name: "web-01" })).toBeInTheDocument());
    const eventItems = await screen.findAllByTestId("host-event-item");
    expect(eventItems).toHaveLength(2);
    expect(eventItems[0]).toHaveTextContent("ROTATE_CREDENTIAL");
    expect(eventItems[1]).toHaveTextContent("ENROLLED");
  });
});
