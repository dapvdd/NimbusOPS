import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import Applications from "../Applications";

const authState = vi.hoisted(() => ({ admin: true, operatorId: "operator-1" }));
vi.mock("../../auth/Session", () => ({
  useAdmin: () => authState.admin,
  useSession: () => ({ user: { operator_id: authState.operatorId, role: authState.admin ? "ADMIN" : "VIEWER" } }),
}));

let operatorSequence = 0;
beforeEach(() => {
  authState.admin = true;
  authState.operatorId = `operator-${++operatorSequence}`;
  sessionStorage.clear();
  vi.spyOn(window, "setInterval").mockReturnValue(1 as unknown as number);
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function setup(state = "EXITED") {
  const requests: { url: string; method: string }[] = [];
  let lookupFails = true;
  let status = "RUNNING";
  vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    requests.push({ url, method });
    let body: unknown;
    if (url.includes("/operations/")) {
      if (lookupFails) return { ok: false, status: 503, json: async () => ({ error: { code: "UNAVAILABLE", message: "Operation lookup unavailable" } }) };
      body = { id: "admitted-operation-123", deployment_id: "d-1", host_id: "h-1", op_type: "DEPLOY", status, result: null };
    } else if (method === "POST") body = { operation_id: "admitted-operation-123", deployment_id: "d-1", host_id: "h-1", status: "QUEUED" };
    else if (url.endsWith("/templates")) body = { templates: [{ key: "nginx-demo", name: "Nginx", image: "nginx" }] };
    else if (url.endsWith("/hosts")) body = { hosts: [{ id: "h-1", hostname: "test-host", status: "ONLINE" }] };
    else body = { applications: [{ deployment_id: "d-1", host_id: "h-1", hostname: "test-host", template_key: "nginx-demo", container_name: "demo", container_state: state, app_url: "http://example.test", last_operation: null }], count: 1 };
    return { ok: true, status: 200, json: async () => body };
  }));
  const view = render(<Applications selectedHostId="h-1" />);
  return { requests, view, lookup: (fails: boolean, nextStatus = "RUNNING") => { lookupFails = fails; status = nextStatus; } };
}

it.each(["Deploy", "Start", "Stop"])("retains %s admission after lookup failure and rechecks without repeating the write", async (action) => {
  const { requests, lookup } = setup(action === "Stop" ? "RUNNING" : "EXITED");
  const button = await screen.findByRole("button", { name: action });
  fireEvent.click(button);
  expect(await screen.findByText("admitted-operation-123")).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent(/lookup unavailable/i);
  expect(screen.getByText(/result.*unverified/i)).toBeInTheDocument();
  expect(button).toBeDisabled();
  const scope = action === "Deploy" ? screen.getByText("Deploy new application").closest("section")! : screen.getByTestId("app-row");
  lookup(false, "SUCCEEDED");
  fireEvent.click(within(scope).getByRole("button", { name: /recheck operation/i }));
  await waitFor(() => expect(within(scope).queryByRole("alert")).not.toBeInTheDocument());
  expect(await within(scope).findByText(/succeeded/i)).toBeInTheDocument();
  expect(requests.filter(r => r.method === "POST")).toHaveLength(1);
  expect(requests.some(r => r.url.endsWith("/operations/admitted-operation-123") && r.method === "GET")).toBe(true);
});

it("makes polling failures visible and recoverable without resubmitting deployment", async () => {
  const { requests, lookup } = setup();
  lookup(false);
  fireEvent.click(await screen.findByRole("button", { name: "Deploy" }));
  expect(await screen.findByTestId("op-progress")).toHaveTextContent(/running/i);
  lookup(true);
  expect(await screen.findByRole("alert", {}, { timeout: 3_500 })).toHaveTextContent(/lookup unavailable/i);
  expect(screen.getByRole("button", { name: "Deploy" })).toBeDisabled();
  lookup(false, "SUCCEEDED");
  fireEvent.click(screen.getByRole("button", { name: /recheck operation/i }));
  expect(await screen.findByTestId("op-success")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(requests.filter(r => r.method === "POST")).toHaveLength(1);
});

it.each(["Deploy", "Start", "Stop"])("keeps %s writes blocked for UNKNOWN results while allowing read-only recheck", async action => {
  const { requests, lookup } = setup(action === "Stop" ? "RUNNING" : "EXITED");
  lookup(false, "UNKNOWN");
  fireEvent.click(await screen.findByRole("button", { name: action }));
  expect(await screen.findByText(/result is unverified/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: action })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: action }));
  fireEvent.click(screen.getByRole("button", { name: /recheck operation/i }));
  await waitFor(() => expect(requests.filter(r => r.url.includes("/operations/"))).toHaveLength(2));
  expect(requests.filter(r => r.method === "POST")).toHaveLength(1);
});

it.each(["Deploy", "Start", "Stop"])("recovers %s admission across unmount/remount without repeating an uncertain write", async action => {
  const { requests, view, lookup } = setup(action === "Stop" ? "RUNNING" : "EXITED");
  fireEvent.click(await screen.findByRole("button", { name: action }));
  await screen.findByRole("alert");
  view.unmount();
  render(<Applications selectedHostId="h-1" />);
  expect(await screen.findByText("admitted-operation-123")).toBeInTheDocument();
  const button = await screen.findByRole("button", { name: action });
  expect(button).toBeDisabled();
  fireEvent.click(button);
  await screen.findByRole("alert");
  lookup(false, "SUCCEEDED");
  fireEvent.click(screen.getByRole("button", { name: /recheck operation/i }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(requests.filter(r => r.method === "POST")).toHaveLength(1);
});

it("does not reveal another operator's admitted operation after remount", async () => {
  const { view } = setup();
  fireEvent.click(await screen.findByRole("button", { name: "Deploy" }));
  await screen.findByRole("alert");
  view.unmount();
  authState.operatorId = "different-operator";
  render(<Applications selectedHostId="h-1" />);
  expect(await screen.findByRole("button", { name: "Deploy" })).toBeEnabled();
  expect(screen.queryByText("admitted-operation-123")).not.toBeInTheDocument();
});

it("keeps deployment admission scoped to its host and stores only identifiers", async () => {
  const { view } = setup();
  fireEvent.click(await screen.findByRole("button", { name: "Deploy" }));
  await screen.findByRole("alert");
  expect(sessionStorage.length).toBe(1);
  const key = sessionStorage.key(0)!;
  expect(key).toContain(authState.operatorId);
  expect(key).toContain("deploy:h-1:nginx-demo");
  expect(sessionStorage.getItem(key)).toBe("admitted-operation-123");
  view.unmount();
  render(<Applications selectedHostId="h-2" />);
  expect(await screen.findByRole("button", { name: "Deploy" })).toBeEnabled();
  expect(screen.queryByText("admitted-operation-123")).not.toBeInTheDocument();
});

it("warns when tab persistence fails while retaining the ID and blocking repeats", async () => {
  const { requests } = setup();
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Storage blocked"); });
  fireEvent.click(await screen.findByRole("button", { name: "Deploy" }));
  expect(await screen.findByText(/cannot be saved in this tab/i)).toBeInTheDocument();
  expect(screen.getByText("admitted-operation-123")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Deploy" })).toBeDisabled();
  expect(requests.filter(r => r.method === "POST")).toHaveLength(1);
});

it.each(["Start", "Stop"])("blocks %s for server UNKNOWN without local admission", async action => {
  setup(action === "Stop" ? "RUNNING" : "EXITED");
  const original = globalThis.fetch;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await original(input, init);
    if (String(input).endsWith("/applications")) {
      const body = await response.json();
      body.applications[0].last_operation = { id: "server-unknown", status: "UNKNOWN", op_type: "DEPLOY" };
      return jsonResponse(body);
    }
    return response;
  }));
  fireEvent.click(await screen.findByRole("button", { name: /refresh state/i }));
  await screen.findByText("Unknown result");
  expect(screen.getByRole("button", { name: action })).toBeDisabled();
});

it("blocks lifecycle writes for an applicable UNKNOWN deploy admission", async () => {
  const { lookup, requests } = setup();
  lookup(false, "UNKNOWN");
  fireEvent.click(await screen.findByRole("button", { name: "Deploy" }));
  await screen.findByTestId("op-unknown");
  const start = screen.getByRole("button", { name: "Start" });
  expect(start).toBeDisabled();
  fireEvent.click(start);
  expect(requests.filter(r => r.method === "POST")).toHaveLength(1);
});

it.each(["Deploy", "Start", "Stop"])("reconciles deferred %s admission after remount and blocks a second POST", async action => {
  const { requests, view } = setup(action === "Stop" ? "RUNNING" : "EXITED");
  const original = globalThis.fetch;
  let resolvePost!: (value: Awaited<ReturnType<typeof fetch>>) => void;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "POST") {
      requests.push({ url: String(input), method: "POST" });
      return new Promise(resolve => { resolvePost = resolve; });
    }
    return original(input, init);
  }));
  fireEvent.click(await screen.findByRole("button", { name: action }));
  view.unmount();
  render(<Applications selectedHostId="h-1" />);
  const replacement = await screen.findByRole("button", { name: action });
  expect(replacement).toBeDisabled();
  fireEvent.click(replacement);
  await act(async () => { resolvePost(jsonResponse({ operation_id: "late-admission" }) as Response); });
  expect(await screen.findByText("late-admission")).toBeInTheDocument();
  expect(requests.filter(r => r.method === "POST")).toHaveLength(1);
});

it("hides and stops polling lifecycle admissions as VIEWER and recovers on ADMIN return", async () => {
  const { requests, view } = setup();
  fireEvent.click(await screen.findByRole("button", { name: "Start" }));
  await screen.findByRole("alert");
  authState.admin = false;
  view.rerender(<Applications selectedHostId="h-1" />);
  expect(screen.queryByText("admitted-operation-123")).not.toBeInTheDocument();
  const reads = requests.filter(r => r.url.includes("/operations/")).length;
  await act(async () => { await new Promise(resolve => window.setTimeout(resolve, 2100)); });
  expect(requests.filter(r => r.url.includes("/operations/"))).toHaveLength(reads);
  authState.admin = true;
  view.rerender(<Applications selectedHostId="h-1" />);
  expect(await screen.findByText("admitted-operation-123")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Start" })).toBeDisabled();
});

it("fails closed with a recovery warning when admission storage cannot be read", async () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("Storage blocked"); });
  setup();
  expect(await within((await screen.findByText("Deploy new application")).closest("section")!).findByText(/cannot read.*admission/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Deploy" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Start" })).toBeDisabled();
});

// Original HEAD regression coverage, retained alongside admission regressions.
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
  it("does not invent container running when successful result has no state", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/applications/deploy")) return Promise.resolve(jsonResponse({ operation_id: "op-no-state" }));
      if (url.includes("/operations/op-no-state")) return Promise.resolve(jsonResponse({ id: "op-no-state", op_type: "DEPLOY", status: "SUCCEEDED", result: null }));
      if (url.includes("/templates")) return Promise.resolve(jsonResponse(templates));
      if (url.includes("/applications")) return Promise.resolve(jsonResponse({ applications: [], count: 0 }));
      if (url.includes("/hosts")) return Promise.resolve(jsonResponse(hosts));
      return Promise.resolve(jsonResponse({}, 404));
    }));
    renderView();
    fireEvent.click(await screen.findByRole("button", { name: /^deploy$/i }));
    const result = await screen.findByTestId("op-success");
    expect(result).toHaveTextContent("Succeeded");
    expect(result).not.toHaveTextContent("container running");
  });
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

describe("Applications — role and lifecycle status consumers", () => {
  it("VIEWER has no deploy, start, or stop control in the DOM", async () => {
    authState.admin = false;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/templates")) return Promise.resolve(jsonResponse(templates));
        if (url.includes("/applications")) return Promise.resolve(jsonResponse({ applications: [runningApp], count: 1 }));
        if (url.includes("/hosts")) return Promise.resolve(jsonResponse(hosts));
        return Promise.resolve(jsonResponse({}, 404));
      }),
    );
    renderView();

    await screen.findByText(runningApp.container_name);
    expect(screen.queryByText(/deploy new application/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^deploy$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^start$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^stop$/i })).not.toBeInTheDocument();
    // Read-only affordances remain.
    expect(screen.getByRole("button", { name: /refresh state/i })).toBeInTheDocument();
  });

  it("a revoked host says re-enroll is required instead of promising a later run", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/templates")) return Promise.resolve(jsonResponse(templates));
        if (url.includes("/applications")) return Promise.resolve(jsonResponse(noApps));
        if (url.includes("/hosts")) {
          return Promise.resolve(jsonResponse({ hosts: [{ id: "h-rev", hostname: "revoked-vm", status: "REVOKED" }], count: 1 }));
        }
        return Promise.resolve(jsonResponse({}, 404));
      }),
    );
    render(
      <MemoryRouter>
        <Applications selectedHostId="h-rev" />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/re-enroll required/i)).toBeInTheDocument();
    expect(screen.queryByText(/will run when the agent reconnects/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^deploy$/i })).toBeDisabled();
  });
});
