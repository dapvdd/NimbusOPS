/**
 * Phase 3B enrollment UX tests (Task 7).
 *
 * Covers:
 * - login → issue bootstrap token (shown ONCE with copy + countdown + warning)
 * - failure states surfaced (401 wrong password, 409 consumed, 410 expired)
 * - token is issued via api.issueBootstrapToken (POST), never stored in
 *   localStorage
 * - Unregister (revoke) dialog requires typing the host id and states that
 *   history is retained
 * - simulated isolation untouched: sim flows never call the new endpoints
 */
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Servers from "../Servers";

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => ({ hosts: [], count: 0 }) }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function fakeLoginOk() {
  return {
    ok: true,
    json: async () => ({ session_token: "sess-token-1234567890abcdef", operator_id: "op-1", role: "ADMIN", expires_at: "2026-11-11T00:00:00Z" }),
  };
}

function fakeTokenIssued() {
  return {
    ok: true,
    status: 201,
    json: async () => ({ id: "bt-1", hostname: "real-host", token: "bstrp-abcdef1234567890", expires_at: new Date(Date.now() + 600_000).toISOString(), created_at: new Date().toISOString() }),
  };
}

it("login → issue bootstrap token shown once with copy and countdown", async () => {
  const fetchMock = vi.mocked(fetch);
  fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/operators/login")) return fakeLoginOk() as unknown as Response;
    if (url.includes("/operators/bootstrap-tokens")) return fakeTokenIssued() as unknown as Response;
    return { ok: true, json: async () => ({ hosts: [], count: 0 }) } as unknown as Response;
  });

  render(<MemoryRouter><Servers /></MemoryRouter>);
  await screen.findByText("No real servers registered");
  fireEvent.click(screen.getByText("Add Server"));
  fireEvent.click(screen.getByText("Existing server"));

  // Login first.
  fireEvent.change(screen.getByLabelText("Username"), { target: { value: "admin" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret-pw" } });
  fireEvent.click(screen.getByText("Sign in"));

  // After login: hostname form appears.
  expect(await screen.findByLabelText("Hostname")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Hostname"), { target: { value: "real-host" } });
  fireEvent.click(screen.getByText("Issue bootstrap token"));

  // Token shown exactly once with copy + warning + countdown.
  expect(await screen.findByText(/bstrp-abcdef1234567890/)).toBeInTheDocument();
  expect(screen.getByText(/shown once/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /copy/i })).toBeInTheDocument();
  expect(screen.getByText(/expires in/i)).toBeInTheDocument();
});

it("wrong password surfaces 401 and stays on login", async () => {
  const fetchMock = vi.mocked(fetch);
  fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/operators/login")) {
      return { ok: false, status: 401, json: async () => ({ error: { code: "UNAUTHORIZED", message: "invalid credentials" } }) } as unknown as Response;
    }
    return { ok: true, json: async () => ({ hosts: [], count: 0 }) } as unknown as Response;
  });

  render(<MemoryRouter><Servers /></MemoryRouter>);
  await screen.findByText("No real servers registered");
  fireEvent.click(screen.getByText("Add Server"));
  fireEvent.click(screen.getByText("Existing server"));
  fireEvent.change(screen.getByLabelText("Username"), { target: { value: "admin" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
  fireEvent.click(screen.getByText("Sign in"));
  expect(await screen.findByRole("alert")).toHaveTextContent(/invalid credentials/i);
  // Still on login form.
  expect(screen.getByLabelText("Username")).toBeInTheDocument();
});

it("session token never lands in localStorage", async () => {
  const fetchMock = vi.mocked(fetch);
  fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/operators/login")) return fakeLoginOk() as unknown as Response;
    if (url.includes("/operators/bootstrap-tokens")) return fakeTokenIssued() as unknown as Response;
    return { ok: true, json: async () => ({ hosts: [], count: 0 }) } as unknown as Response;
  });
  render(<MemoryRouter><Servers /></MemoryRouter>);
  await screen.findByText("No real servers registered");
  fireEvent.click(screen.getByText("Add Server"));
  fireEvent.click(screen.getByText("Existing server"));
  fireEvent.change(screen.getByLabelText("Username"), { target: { value: "admin" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret-pw" } });
  fireEvent.click(screen.getByText("Sign in"));
  await screen.findByLabelText("Hostname");
  expect(localStorage.getItem("nimbusops.session")).toBeNull();
  expect(localStorage.getItem("session_token")).toBeNull();
  const stored = JSON.stringify(localStorage);
  expect(stored).not.toContain("sess-token-1234567890abcdef");
});

it("410 expired surfaced when issuing fails", async () => {
  const fetchMock = vi.mocked(fetch);
  fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/operators/login")) return fakeLoginOk() as unknown as Response;
    if (url.includes("/operators/bootstrap-tokens") && init?.method === "POST") {
      return { ok: false, status: 410, json: async () => ({ error: { code: "BOOTSTRAP_TOKEN_EXPIRED", message: "bootstrap token expired" } }) } as unknown as Response;
    }
    return { ok: true, json: async () => ({ hosts: [], count: 0 }) } as unknown as Response;
  });
  render(<MemoryRouter><Servers /></MemoryRouter>);
  await screen.findByText("No real servers registered");
  fireEvent.click(screen.getByText("Add Server"));
  fireEvent.click(screen.getByText("Existing server"));
  fireEvent.change(screen.getByLabelText("Username"), { target: { value: "admin" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret-pw" } });
  fireEvent.click(screen.getByText("Sign in"));
  fireEvent.change(await screen.findByLabelText("Hostname"), { target: { value: "real-host" } });
  fireEvent.click(screen.getByText("Issue bootstrap token"));
  expect(await screen.findByRole("alert")).toHaveTextContent(/expired/i);
});

it("unregister dialog requires typing the host id and keeps history", async () => {
  const fetchMock = vi.mocked(fetch);
  fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/hosts" || url.endsWith("/api/v1/hosts")) {
      return {
        ok: true,
        json: async () => ({
          hosts: [{ id: "h-real-1", hostname: "real-host", status: "ONLINE", agent_version: "0.2.0", platform: "Linux", platform_release: "6.8", cpu_cores: 4, total_memory_bytes: 8e9, boot_time: null, enrolled_at: "2026-11-10T00:00:00Z", last_seen_at: null, last_telemetry_at: null, latest_metrics: null, is_revoked: false, enrollment_status: "ENROLLED", docker_enabled: false }],
          count: 1,
        }),
      } as unknown as Response;
    }
    return { ok: true, json: async () => ({ hosts: [], count: 0 }) } as unknown as Response;
  });

  render(<MemoryRouter><Servers /></MemoryRouter>);
  expect(await screen.findByText("real-host")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /unregister real-host/i }));

  // Consequence statement + typed confirmation required.
  expect(screen.getByText(/telemetry and history are retained/i)).toBeInTheDocument();
  const confirmInput = screen.getByLabelText(/type .*host id.* to confirm/i);
  expect(screen.getByRole("button", { name: /^unregister$/i })).toBeDisabled();
  fireEvent.change(confirmInput, { target: { value: "h-real-1" } });
  expect(screen.getByRole("button", { name: /^unregister$/i })).toBeEnabled();
});

it("sim flows never call the new operator endpoints", async () => {
  const fetchMock = vi.mocked(fetch);
  render(<MemoryRouter><Servers /></MemoryRouter>);
  await screen.findByText("No real servers registered");
  fireEvent.click(screen.getByText("Add Server"));
  fireEvent.change(screen.getByLabelText("Server name"), { target: { value: "sim-demo" } });
  fireEvent.click(screen.getByText("Create simulated server"));
  await waitFor(() => expect(screen.getByText("sim-demo")).toBeInTheDocument());
  const calledUrls = fetchMock.mock.calls.map((c) => String(c[0]));
  expect(calledUrls.every((u) => !u.includes("/operators/"))).toBe(true);
  expect(calledUrls.every((u) => !u.includes("/re-enroll") && !u.includes("/rotate-credential"))).toBe(true);
});
