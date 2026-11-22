import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Settings from "../Settings";
import { SessionProvider } from "../../auth/Session";

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

const HEALTH_OK = {
  status: "ok",
  service: "nimbusops",
  version: "0.1.0",
  build: "test-build",
  server_time: "2026-11-17T00:00:00Z",
  database: "ok",
};

const READY_OK = { ready: true, database: "ok", version: "0.1.0" };
const READY_DEGRADED = { ready: false, database: "degraded", version: "0.1.0" };

function stubApi(overrides: { ready?: () => ReturnType<typeof jsonResponse> } = {}) {
  return vi.fn(async (url: string, _init?: RequestInit) => {
    const path = String(url);
    if (path.includes("/operators/me")) {
      return jsonResponse({ operator_id: "op-1", username: "admin", role: "ADMIN" });
    }
    if (path.includes("/operators/session/csrf")) return jsonResponse({ csrf_token: "csrf-1" });
    if (path.includes("/operators/session/logout")) return jsonResponse({ ok: true });
    if (path.includes("/ready")) return overrides.ready ? overrides.ready() : jsonResponse(READY_OK);
    if (path.includes("/health")) return jsonResponse(HEALTH_OK);
    return jsonResponse({});
  });
}

function renderSettings() {
  return render(
    <SessionProvider>
      <MemoryRouter initialEntries={["/settings"]}>
        <Settings />
      </MemoryRouter>
    </SessionProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Settings", () => {
  it("does not retain ready when the health probe becomes unavailable", async () => {
    let fail = false;
    const base = stubApi();
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => fail && String(url).endsWith('/health')
      ? Promise.resolve(jsonResponse({}, 502)) : base(url, init)));
    renderSettings();
    await screen.findByTestId('readiness-ok');
    fail = true;
    fireEvent.click(screen.getByRole('button', {name: /recheck/i}));
    expect(await screen.findByRole('alert')).toHaveTextContent(/Health probe unavailable/);
    expect(screen.queryByTestId('readiness-ok')).not.toBeInTheDocument();
  });
  it("reports sign-out failure without pretending the session ended", async () => {
    const base = stubApi();
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => String(url).includes('/session/logout')
      ? Promise.resolve(jsonResponse({error: {message: 'Logout unavailable'}}, 503)) : base(url, init)));
    renderSettings();
    fireEvent.click(await screen.findByRole('button', {name: /sign out/i}));
    expect(await screen.findByRole('alert')).toHaveTextContent(/sign.out failed/i);
    expect(screen.getByTestId('settings-account')).toHaveTextContent('admin');
  });
  it("does not claim ready when the readiness probe is unavailable", async () => {
    vi.stubGlobal("fetch", stubApi({ ready: () => jsonResponse({}, 502) }));
    renderSettings();
    expect(await screen.findByRole("alert")).toHaveTextContent(/readiness/i);
    expect(screen.queryByTestId("readiness-ok")).not.toBeInTheDocument();
  });

  it("clears stale readiness after a failed recheck", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", stubApi({ ready: () => ++calls === 1 ? jsonResponse(READY_OK) : jsonResponse({}, 502) }));
    renderSettings();
    await screen.findByTestId("readiness-ok");
    fireEvent.click(screen.getByRole("button", { name: /recheck/i }));
    await screen.findByRole("alert");
    expect(screen.queryByTestId("readiness-ok")).not.toBeInTheDocument();
  });
  it("renders the signed-in operator from the real session", async () => {
    vi.stubGlobal("fetch", stubApi());
    renderSettings();
    const account = await screen.findByTestId("settings-account");
    expect(account).toHaveTextContent("admin");
    expect(account).toHaveTextContent(/admin/i);
  });

  it("signs out through the session endpoint with a CSRF header", async () => {
    const fetchMock = stubApi();
    vi.stubGlobal("fetch", fetchMock);
    renderSettings();

    const signOut = await screen.findByRole("button", { name: /sign out/i });
    fireEvent.click(signOut);

    await waitFor(() => {
      const logoutCall = fetchMock.mock.calls.find(([url]) => String(url).includes("/operators/session/logout"));
      expect(logoutCall).toBeTruthy();
    });
    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).includes("/operators/session/logout"))!;
    expect(init?.method).toBe("POST");
    expect((init?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-1");
  });

  it("renders a 503 readiness probe as degraded data with recovery steps, not an error", async () => {
    vi.stubGlobal("fetch", stubApi({ ready: () => jsonResponse(READY_DEGRADED, 503) }));
    renderSettings();

    const panel = await screen.findByTestId("readiness-degraded");
    expect(panel).toHaveTextContent(/degraded/i);
    expect(panel).not.toHaveTextContent(/cannot reach/i);
    expect(screen.getByTestId("readiness-recovery")).toHaveTextContent(/NIMBUSOPS_DATABASE_URL/i);
    expect(screen.getByTestId("readiness-recovery")).toHaveTextContent(/logs/i);
    // A degraded control plane is diagnosed, never restarted from the UI.
    expect(screen.queryByRole("button", { name: /restart/i })).not.toBeInTheDocument();
  });

  it("rechecks readiness on demand and shows the recovered state", async () => {
    let readyCalls = 0;
    const fetchMock = stubApi({
      ready: () => {
        readyCalls += 1;
        return readyCalls === 1 ? jsonResponse(READY_DEGRADED, 503) : jsonResponse(READY_OK);
      },
    });
    vi.stubGlobal("fetch", fetchMock);
    renderSettings();

    await screen.findByTestId("readiness-degraded");
    fireEvent.click(screen.getByRole("button", { name: /recheck/i }));

    await screen.findByTestId("readiness-ok");
    expect(screen.queryByTestId("readiness-degraded")).not.toBeInTheDocument();
    expect(readyCalls).toBeGreaterThanOrEqual(2);
  });

  it("documents the reviewed deployment examples as copyable paths, not dead app routes", async () => {
    vi.stubGlobal("fetch", stubApi());
    renderSettings();

    const reference = await screen.findByTestId("deployment-reference");
    // Real artifact names from deploy/examples — no invented unit names.
    expect(reference).toHaveTextContent(/nimbusops-api\.service\.example/);
    expect(reference).toHaveTextContent(/nimbusops-agent-telemetry\.service\.example/);
    expect(reference).not.toHaveTextContent(/nimbusops-backend/);
    // The environment contract uses the backend's real NIMBUSOPS_ prefix.
    expect(reference).toHaveTextContent(/NIMBUSOPS_DATABASE_URL=/);
    expect(reference).toHaveTextContent(/NIMBUSOPS_BROWSER_ORIGINS=/);
    expect(reference).not.toHaveTextContent(/NIMBOPS_(?!S)/);
    expect(reference).toHaveTextContent(/Nothing is installed by NimbusOps/i);
    expect(reference.querySelectorAll('a[href*="deploy/examples"]').length).toBe(0);
  });
});
