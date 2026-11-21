import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ManualOnboarding as Onboarding } from "../Onboarding";

vi.mock("../../auth/Session", () => ({
  useAdmin: () => true,
  useSession: () => ({ user: { role: "ADMIN", operator_id: "op-1" } }),
  Protected: ({ children }: any) => children,
}));

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("Onboarding wizard", () => {
  it("accepts an explicit target-local CA path", () => {
    render(<MemoryRouter><Onboarding /></MemoryRouter>);
    const input = screen.getByLabelText(/private CA bundle path/i);
    fireEvent.change(input, { target: { value: "/etc/nimbusops/ca.pem" } });
    expect(input).toHaveValue("/etc/nimbusops/ca.pem");
  });
  it("requires explicit confirmation before re-enroll issuance", async () => {
    const { api } = await import("../../api/client");
    vi.spyOn(api, "listHosts").mockResolvedValue({ hosts: [{ id: "h-revoked", hostname: "demo.example.org", status: "OFFLINE", is_revoked: true }], total: 1 } as any);
    vi.spyOn(api, "listBootstrapTokens").mockResolvedValue({ tokens: [{ id: "bt-re", hostname: "demo.example.org" }] } as any);
    const issue = vi.spyOn(api, "reenrollHost").mockResolvedValue({ bootstrap_token: "disposable", expires_at: new Date(Date.now() + 600000).toISOString() } as any);
    render(<MemoryRouter><Onboarding /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText(/hostname/i), { target: { value: "demo.example.org" } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    await screen.findByText(/already exists in your fleet/i);
    expect(issue).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /confirm re-enroll/i }));
    await waitFor(() => expect(issue).toHaveBeenCalledWith("h-revoked"));
    expect(await screen.findByText("disposable")).toBeInTheDocument();
  });
  it("duplicate hostname at step 1 warns and provides open host / re-enroll paths", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string) => {
        const url = String(input);
        if (url.endsWith("/hosts")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              hosts: [{ id: "h-existing", hostname: "existing-box", status: "ONLINE" }],
              total: 1,
            }),
          };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      })
    );

    render(
      <MemoryRouter initialEntries={["/servers/new"]}>
        <Routes>
          <Route path="/servers/new" element={<Onboarding />} />
        </Routes>
      </MemoryRouter>
    );

    const input = screen.getByLabelText(/hostname/i);
    fireEvent.change(input, { target: { value: "existing-box" } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));

    expect(await screen.findByText(/already exists in your fleet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open host/i })).toHaveAttribute(
      "href",
      "/servers/h-existing"
    );
  });

  it("issues real token at step 3 with no token in install commands", async () => {
    const fetchRequests: { url: string; body?: any; method?: string }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string, init?: RequestInit) => {
        const url = String(input);
        fetchRequests.push({ url, method: init?.method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
        if (url.endsWith("/hosts")) {
          return { ok: true, status: 200, json: async () => ({ hosts: [], total: 0 }) };
        }
        if (url.includes("/operators/bootstrap-tokens") && init?.method === "POST") {
          return {
            ok: true,
            status: 201,
            json: async () => ({
              id: "bt-new-1",
              hostname: "new-server",
              token: "bstrp_secret_token_12345",
              expires_at: new Date(Date.now() + 600_000).toISOString(),
            }),
          };
        }
        if (url.includes("/operators/bootstrap-tokens")) {
          return { ok: true, status: 200, json: async () => ({ tokens: [], count: 0 }) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      })
    );

    render(
      <MemoryRouter initialEntries={["/servers/new"]}>
        <Routes>
          <Route path="/servers/new" element={<Onboarding />} />
        </Routes>
      </MemoryRouter>
    );

    // Step 1: Host
    fireEvent.change(screen.getByLabelText(/hostname/i), { target: { value: "new-server" } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));

    // Step 2: Mode
    expect(await screen.findByText(/telemetry only/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /generate enrollment token/i }));

    // Step 3: Token
    await waitFor(() => {
      const issueReq = fetchRequests.find((r) => r.method === "POST");
      expect(issueReq).toBeDefined();
      expect(issueReq?.body).toEqual({ hostname: "new-server" });
    });
    expect(await screen.findByText("bstrp_secret_token_12345")).toBeInTheDocument();
    expect(screen.getByText(/cannot be shown again/i)).toBeInTheDocument();

    // Advance to Step 4: Install
    fireEvent.click(screen.getByRole("button", { name: /continue to installation/i }));

    // Step 4: Install commands
    expect(await screen.findByText(/prompt-to-file/i)).toBeInTheDocument();
    const allCodeText = Array.from(document.querySelectorAll("code, pre"))
      .map((el) => el.textContent)
      .join("\n");
    expect(allCodeText).not.toContain("bstrp_secret_token_12345");
    expect(allCodeText).not.toContain("--token");
  });

  it("does not issue a token when the duplicate check could not run", async () => {
    let listFailedOnce = true; // first Continue: fleet lookup fails
    const postIssued: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/hosts")) {
          if (listFailedOnce) {
            listFailedOnce = false;
            return { ok: false, status: 503, json: async () => ({ error: { code: "UNAVAILABLE", message: "control plane busy" } }) };
          }
          return { ok: true, status: 200, json: async () => ({ hosts: [], total: 0 }) };
        }
        if (url.includes("/operators/bootstrap-tokens") && init?.method === "POST") {
          postIssued.push(url);
          return {
            ok: true,
            status: 201,
            json: async () => ({ id: "bt-x", hostname: "blocked-host", token: "tok", expires_at: new Date(Date.now() + 600_000).toISOString() }),
          };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      })
    );

    render(
      <MemoryRouter initialEntries={["/servers/new"]}>
        <Routes>
          <Route path="/servers/new" element={<Onboarding />} />
        </Routes>
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText(/hostname/i), { target: { value: "blocked-host" } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));

    // The wizard explains the failure and stays on step 1; no token is issued.
    expect(await screen.findByText(/duplicate check failed/i)).toBeInTheDocument();
    expect(postIssued).toHaveLength(0);

    // Once the fleet is reachable the wizard continues normally.
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(await screen.findByText(/telemetry only/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /generate enrollment token/i }));
    await waitFor(() => expect(postIssued).toHaveLength(1));
  });

  it("handles BOOTSTRAP_TOKEN_ACTIVE with revoke and reissue action", async () => {
    let callCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/hosts")) {
          return { ok: true, status: 200, json: async () => ({ hosts: [], total: 0 }) };
        }
        if (url.includes("/operators/bootstrap-tokens") && init?.method === "POST") {
          callCount++;
          if (callCount === 1) {
            return {
              ok: false,
              status: 409,
              json: async () => ({
                error: {
                  code: "BOOTSTRAP_TOKEN_ACTIVE",
                  message: "Active token already exists",
                },
              }),
            };
          }
          return {
            ok: true,
            status: 201,
            json: async () => ({
              id: "bt-new-2",
              hostname: "active-server",
              token: "bstrp_reissued_token_999",
              expires_at: new Date(Date.now() + 600_000).toISOString(),
            }),
          };
        }
        if (url.includes("/operators/bootstrap-tokens") && init?.method === "DELETE") {
          return { ok: true, status: 200, json: async () => ({ status: "revoked" }) };
        }
        if (url.includes("/operators/bootstrap-tokens")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              tokens: [{ id: "bt-old-active", hostname: "active-server", expires_at: new Date(Date.now() + 300_000).toISOString() }],
              count: 1,
            }),
          };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      })
    );

    render(
      <MemoryRouter initialEntries={["/servers/new"]}>
        <Routes>
          <Route path="/servers/new" element={<Onboarding />} />
        </Routes>
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText(/hostname/i), { target: { value: "active-server" } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    fireEvent.click(await screen.findByRole("button", { name: /generate enrollment token/i }));

    expect(await screen.findByText(/another enrollment token is still active/i)).toBeInTheDocument();
    const revokeBtn = screen.getByRole("button", { name: /revoke and reissue/i });
    fireEvent.click(revokeBtn);

    expect(await screen.findByText("bstrp_reissued_token_999")).toBeInTheDocument();
  });

  it("verify step requires the consumed host and fresh telemetry", async () => {
    let hostRegistered = false;
    const consumedAt = new Date(Date.now() - 10_000).toISOString();
    const observedAt = new Date().toISOString();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/hosts")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              hosts: hostRegistered
                ? [{ id: "h-ready-1", hostname: "ready-server", status: "ONLINE",
                    is_revoked: false, enrollment_status: "ENROLLED",
                    last_seen_at: observedAt, last_telemetry_at: observedAt,
                    latest_metrics: { cpu_percent: 10, recorded_at: observedAt } }]
                : [],
              total: hostRegistered ? 1 : 0,
            }),
          };
        }
        if (url.includes("/operators/bootstrap-tokens") && init?.method === "POST") {
          return {
            ok: true,
            status: 201,
            json: async () => ({
              id: "bt-ready-1",
              hostname: "ready-server",
              token: "bstrp_ready_123",
              expires_at: new Date(Date.now() + 600_000).toISOString(),
            }),
          };
        }
        if (url.includes("/operators/bootstrap-tokens")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              tokens: [
                {
                  id: "bt-ready-1",
                  hostname: "ready-server",
                  expires_at: new Date(Date.now() + 600_000).toISOString(),
                  consumed_at: hostRegistered ? consumedAt : null,
                  consumed_by_host_id: hostRegistered ? "h-ready-1" : null,
                },
              ],
              count: 1,
            }),
          };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      })
    );

    render(
      <MemoryRouter initialEntries={["/servers/new"]}>
        <Routes>
          <Route path="/servers/new" element={<Onboarding />} />
        </Routes>
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText(/hostname/i), { target: { value: "ready-server" } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    fireEvent.click(await screen.findByRole("button", { name: /generate enrollment token/i }));
    fireEvent.click(await screen.findByRole("button", { name: /continue to installation/i }));
    fireEvent.click(await screen.findByRole("button", { name: /verify enrollment/i }));

    // Step 5: Verify
    expect(await screen.findByText(/waiting for agent enrollment/i)).toBeInTheDocument();
    const continueBtn = screen.getByRole("button", { name: /continue to host/i });
    expect(continueBtn).toBeDisabled();

    // Now host registers
    hostRegistered = true;
    fireEvent.click(screen.getByRole("button", { name: /refresh status/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /continue to host/i })).toBeEnabled();
    });
  });
});
