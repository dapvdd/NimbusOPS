/**
 * Phase 2 frontend tests: Applications view. Mocked fetch (no backend).
 * Verifies templates, deploy interaction, operation feedback, lifecycle
 * controls, and honest state display.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Applications from "../Applications";

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

const templates = {
  templates: [
    {
      key: "nginx-demo",
      name: "Nginx Demo",
      description: "Deterministic single-container Nginx.",
      image: "nginx:1.27-alpine",
      container_port: 80,
      host_port: 18080,
      is_approved: true,
    },
  ],
};

const hosts = {
  hosts: [
    { id: "h-1", hostname: "web-01", status: "ONLINE" },
    { id: "h-2", hostname: "db-01", status: "OFFLINE" },
  ],
  count: 2,
};

const noApps = { applications: [], count: 0 };

const runningApp = {
  deployment_id: "dep-1",
  host_id: "h-1",
  hostname: "web-01",
  template_key: "nginx-demo",
  container_name: "nimbusops-nginx-demo-abc12345",
  app_url: "http://localhost:18080/",
  last_operation: {
    id: "op-1",
    deployment_id: "dep-1",
    host_id: "h-1",
    op_type: "DEPLOY",
    status: "SUCCEEDED",
    created_at: "2026-11-08T10:00:00Z",
    updated_at: "2026-11-08T10:01:00Z",
    completed_at: "2026-11-08T10:01:00Z",
    result: { container_state: "RUNNING", http_ok: true, app_url: "http://localhost:18080/" },
    error_code: null,
    error_message: null,
  },
  container_state: "RUNNING",
  http_ok: true,
  reported_at: "2026-11-08T10:01:00Z",
};

const stoppedApp = {
  ...runningApp,
  deployment_id: "dep-2",
  container_name: "nimbusops-nginx-demo-def67890",
  container_state: "EXITED",
  http_ok: null,
  last_operation: {
    ...runningApp.last_operation,
    id: "op-2",
    status: "SUCCEEDED",
    result: { container_state: "EXITED", http_ok: null },
  },
};

beforeEach(() => {
  vi.spyOn(window, "setInterval").mockReturnValue(1 as unknown as number);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function renderView() {
  return render(
    <MemoryRouter>
      <Applications />
    </MemoryRouter>,
  );
}

describe("Applications — rendering", () => {
  it("renders loading state first", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    renderView();
    expect(screen.getByTestId("loading-panel")).toBeInTheDocument();
  });

  it("renders templates, host selector, and empty app list", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/templates")) return Promise.resolve(jsonResponse(templates));
        if (url.includes("/applications")) return Promise.resolve(jsonResponse(noApps));
        if (url.includes("/hosts")) return Promise.resolve(jsonResponse(hosts));
        return Promise.resolve(jsonResponse({}, 404));
      }),
    );
    renderView();
    await waitFor(() => expect(screen.getByText(/deploy new application/i)).toBeInTheDocument());
    expect(screen.getByRole("combobox", { name: /template/i })).toBeInTheDocument();
    expect(screen.getByTestId("empty-panel")).toBeInTheDocument();
  });

  it("renders error state when API unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("network down");
      }),
    );
    renderView();
    await waitFor(() => expect(screen.getByTestId("error-panel")).toBeInTheDocument());
  });
});

describe("Applications — deploy interaction", () => {
  it("deploy click POSTs and shows queued/running progress then success", async () => {
    const deployBody = {
      operation_id: "op-new",
      deployment_id: "dep-1",
      host_id: "h-1",
      template_key: "nginx-demo",
      status: "QUEUED",
      container_name: "nimbusops-nginx-demo-abc12345",
      app_url: "http://localhost:18080/",
      deduplicated: false,
    };
    const opQueued = {
      id: "op-new",
      deployment_id: "dep-1",
      host_id: "h-1",
      op_type: "DEPLOY",
      status: "QUEUED",
      created_at: "2026-11-08T10:00:00Z",
      updated_at: "2026-11-08T10:00:00Z",
      completed_at: null,
      result: null,
      error_code: null,
      error_message: null,
    };
    const opDone = { ...opQueued, status: "SUCCEEDED", result: { http_ok: true } };
    let opPolls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (url.includes("/applications/deploy") && init?.method === "POST") {
          return Promise.resolve(jsonResponse(deployBody));
        }
        if (url.includes("/operations/op-new")) {
          opPolls += 1;
          return Promise.resolve(jsonResponse(opPolls === 1 ? opQueued : opDone));
        }
        if (url.includes("/templates")) return Promise.resolve(jsonResponse(templates));
        if (url.includes("/applications") && !init?.method) {
          return Promise.resolve(jsonResponse({ applications: [runningApp], count: 1 }));
        }
        if (url.includes("/hosts")) return Promise.resolve(jsonResponse(hosts));
        return Promise.resolve(jsonResponse({}, 404));
      }),
    );
    renderView();
    const deployBtn = await screen.findByRole("button", { name: /deploy/i });
    fireEvent.click(deployBtn);
    await waitFor(() => expect(screen.getByTestId("operation-panel")).toBeInTheDocument());
    // Queued feedback first.
    await waitFor(() => expect(screen.getByTestId("op-progress")).toBeInTheDocument());
    // Terminal feedback after the poll flip.
    await waitFor(() => expect(screen.getByTestId("op-success")).toBeInTheDocument(), { timeout: 3000 });
  });

  it("shows failure feedback with error code", async () => {
    const opFailed = {
      id: "op-new",
      deployment_id: "dep-1",
      host_id: "h-1",
      op_type: "DEPLOY",
      status: "FAILED",
      created_at: "2026-11-08T10:00:00Z",
      updated_at: "2026-11-08T10:00:00Z",
      completed_at: "2026-11-08T10:01:00Z",
      result: null,
      error_code: "PORT_CONFLICT",
      error_message: "host port 8080 unavailable",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (url.includes("/applications/deploy") && init?.method === "POST") {
          return Promise.resolve(
            jsonResponse({
              operation_id: "op-new",
              deployment_id: "dep-1",
              host_id: "h-1",
              template_key: "nginx-demo",
              status: "QUEUED",
              container_name: "nimbusops-nginx-demo-abc12345",
              app_url: "http://localhost:18080/",
              deduplicated: false,
            }),
          );
        }
        if (url.includes("/operations/op-new")) return Promise.resolve(jsonResponse(opFailed));
        if (url.includes("/templates")) return Promise.resolve(jsonResponse(templates));
        if (url.includes("/applications") && !init?.method) return Promise.resolve(jsonResponse(noApps));
        if (url.includes("/hosts")) return Promise.resolve(jsonResponse(hosts));
        return Promise.resolve(jsonResponse({}, 404));
      }),
    );
    renderView();
    const deployBtn = await screen.findByRole("button", { name: /deploy/i });
    fireEvent.click(deployBtn);
    await waitFor(() => expect(screen.getByTestId("op-failure")).toBeInTheDocument());
    expect(screen.getByText(/PORT_CONFLICT/)).toBeInTheDocument();
  });

  it("shows unknown-result feedback", async () => {
    const opUnknown = {
      id: "op-new",
      deployment_id: "dep-1",
      host_id: "h-1",
      op_type: "DEPLOY",
      status: "UNKNOWN",
      created_at: "2026-11-08T10:00:00Z",
      updated_at: "2026-11-08T10:00:00Z",
      completed_at: "2026-11-08T10:01:00Z",
      result: null,
      error_code: "TIMEOUT",
      error_message: "docker command timed out",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (url.includes("/applications/deploy") && init?.method === "POST") {
          return Promise.resolve(
            jsonResponse({
              operation_id: "op-new",
              deployment_id: "dep-1",
              host_id: "h-1",
              template_key: "nginx-demo",
              status: "QUEUED",
              container_name: "nimbusops-nginx-demo-abc12345",
              app_url: "http://localhost:18080/",
              deduplicated: false,
            }),
          );
        }
        if (url.includes("/operations/op-new")) return Promise.resolve(jsonResponse(opUnknown));
        if (url.includes("/templates")) return Promise.resolve(jsonResponse(templates));
        if (url.includes("/applications") && !init?.method) return Promise.resolve(jsonResponse(noApps));
        if (url.includes("/hosts")) return Promise.resolve(jsonResponse(hosts));
        return Promise.resolve(jsonResponse({}, 404));
      }),
    );
    renderView();
    const deployBtn = await screen.findByRole("button", { name: /deploy/i });
    fireEvent.click(deployBtn);
    await waitFor(() => expect(screen.getByTestId("op-unknown")).toBeInTheDocument());
  });
});

describe("Applications — lifecycle controls", () => {
  it("stop enabled when running, start disabled; stop click POSTs", async () => {
    const stopCalls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (url.includes("/applications/dep-1/stop") && init?.method === "POST") {
          stopCalls.push(url);
          return Promise.resolve(
            jsonResponse({
              operation_id: "op-stop",
              deployment_id: "dep-1",
              host_id: "h-1",
              template_key: "nginx-demo",
              status: "QUEUED",
              container_name: "nimbusops-nginx-demo-abc12345",
              app_url: "http://localhost:18080/",
              deduplicated: false,
            }),
          );
        }
        if (url.includes("/templates")) return Promise.resolve(jsonResponse(templates));
        if (url.includes("/applications") && !init?.method) {
          return Promise.resolve(jsonResponse({ applications: [runningApp], count: 1 }));
        }
        if (url.includes("/hosts")) return Promise.resolve(jsonResponse(hosts));
        return Promise.resolve(jsonResponse({}, 404));
      }),
    );
    renderView();
    const stopBtn = await screen.findByRole("button", { name: /^stop$/i });
    await waitFor(() => expect(stopBtn).not.toBeDisabled());
    const startBtn = screen.getByRole("button", { name: /^start$/i });
    expect(startBtn).toBeDisabled();
    fireEvent.click(stopBtn);
    await waitFor(() => expect(stopCalls.length).toBe(1));
  });

  it("start enabled when stopped, stop disabled when stopped", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (url.includes("/templates")) return Promise.resolve(jsonResponse(templates));
        if (url.includes("/applications") && !init?.method) {
          return Promise.resolve(jsonResponse({ applications: [stoppedApp], count: 1 }));
        }
        if (url.includes("/hosts")) return Promise.resolve(jsonResponse(hosts));
        return Promise.resolve(jsonResponse({}, 404));
      }),
    );
    renderView();
    const startBtn = await screen.findByRole("button", { name: /^start$/i });
    await waitFor(() => expect(startBtn).not.toBeDisabled());
    expect(screen.getByRole("button", { name: /^stop$/i })).toBeDisabled();
    expect(screen.getByText(/stopped/i)).toBeInTheDocument();
  });
});
