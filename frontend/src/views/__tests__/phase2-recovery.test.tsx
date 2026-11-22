import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import Servers from "../Servers";
import HostDetail from "../HostDetail";
import { ManualOnboarding } from "../Onboarding";
import Settings from "../Settings";

vi.mock("../../auth/Session", () => ({
  useAdmin: () => true,
  useSession: () => ({ user: { username: "reader", role: "VIEWER" } }),
}));
vi.mock("../../components/HostDocker", () => ({ default: () => null }));
vi.mock("../host/HostActions", () => ({ default: () => null }));

afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });
const wrap = (element: React.ReactNode) => render(<MemoryRouter>{element}</MemoryRouter>);

describe("Phase 2 recovery", () => {
  it("distinguishes unavailable tokens from empty and recovers via retry without hiding hosts", async () => {
    vi.spyOn(api, "listHosts").mockResolvedValue({ hosts: [{ id: "h", hostname: "kept-host", status: "ONLINE" }], total: 1 } as any);
    vi.spyOn(api, "listBootstrapTokens").mockRejectedValueOnce(new Error("tokens unavailable")).mockResolvedValue({ tokens: [], count: 0 });
    wrap(<Servers />);
    expect(await screen.findByText("kept-host")).toBeInTheDocument();
    expect(await screen.findByText(/Enrollment token feed unavailable/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /retry token feed/i }));
    await waitFor(() => expect(screen.queryByText(/Enrollment token feed unavailable/i)).not.toBeInTheDocument());
  });

  it("does not label an unavailable awaiting feed as no registered servers", async () => {
    vi.spyOn(api, "listHosts").mockResolvedValue({ hosts: [], count: 0 });
    vi.spyOn(api, "listBootstrapTokens").mockRejectedValue(new Error("offline"));
    wrap(<Servers />);
    fireEvent.click(screen.getByRole("button", { name: "AWAITING" }));
    await screen.findByText(/Enrollment token feed unavailable/i);
    expect(screen.queryByText("No real servers registered")).not.toBeInTheDocument();
  });

  it("clears event errors after retry and never calls an unavailable feed empty", async () => {
    vi.spyOn(api, "getHost").mockResolvedValue({ id: "h", hostname: "host", status: "ONLINE" } as any);
    vi.spyOn(api, "getHostMetrics").mockResolvedValue({ points: [] } as any);
    vi.spyOn(api, "listHostEvents").mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ events: [], count: 0 });
    render(<MemoryRouter initialEntries={["/hosts/h"]}><Routes><Route path="/hosts/:hostId" element={<HostDetail />} /></Routes></MemoryRouter>);
    const events = await screen.findByRole("region", { name: "Host events" });
    await within(events).findByText("Unable to load events.");
    expect(within(events).queryByText("No events yet")).not.toBeInTheDocument();
    fireEvent.click(within(events).getByRole("button", { name: /retry events/i }));
    expect(await within(events).findByText("No events yet")).toBeInTheDocument();
    expect(within(events).queryByText("Unable to load events.")).not.toBeInTheDocument();
  });

  async function verifyWizard() {
    const now = new Date().toISOString();
    const host = { id: "h", hostname: "new-host", status: "ONLINE", last_seen_at: now, last_telemetry_at: now, latest_metrics: { recorded_at: now } };
    const token = { id: "t", hostname: "new-host", created_at: now, revoked_at: null, expires_at: new Date(Date.now() + 600000).toISOString(), consumed_at: now, consumed_by_host_id: "h" };
    vi.spyOn(api, "listHosts").mockResolvedValueOnce({ hosts: [], count: 0 }).mockResolvedValue({ hosts: [host], count: 1 } as any);
    const tokens = vi.spyOn(api, "listBootstrapTokens").mockResolvedValue({ tokens: [token], count: 1 });
    vi.spyOn(api, "issueBootstrapToken").mockResolvedValue({ ...token, token: "secret" } as any);
    wrap(<ManualOnboarding />);
    fireEvent.change(screen.getByLabelText(/hostname/i), { target: { value: "new-host" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(await screen.findByRole("button", { name: /generate enrollment/i }));
    fireEvent.click(await screen.findByRole("button", { name: /continue to installation/i }));
    fireEvent.click(screen.getByRole("button", { name: /verify enrollment/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /continue to host/i })).toBeEnabled());
    return { tokens, token };
  }

  it("invalidates verified state after a manual refresh failure and recovers", async () => {
    const { tokens, token } = await verifyWizard();
    tokens.mockRejectedValueOnce(new Error("offline"));
    fireEvent.click(screen.getByRole("button", { name: /refresh status/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /continue to host/i })).toBeDisabled());
    expect(screen.getByText(/Verification unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText("Active")).not.toBeInTheDocument();
    tokens.mockResolvedValue({ tokens: [token], count: 1 });
    fireEvent.click(screen.getByRole("button", { name: /refresh status/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /continue to host/i })).toBeEnabled());
    expect(screen.queryByText(/Verification unavailable/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Awaiting connection from/i)).not.toBeInTheDocument();
  });

  it("invalidates verified state after an automatic poll failure", async () => {
    const interval = vi.spyOn(globalThis, "setInterval");
    const { tokens } = await verifyWizard();
    tokens.mockRejectedValue(new Error("offline"));
    const poll = interval.mock.calls.find(([, delay]) => delay === 3000)![0] as () => void;
    await act(async () => { poll(); });
    expect(screen.getByRole("button", { name: /continue to host/i })).toBeDisabled();
    expect(screen.getByText(/Verification unavailable/i)).toBeInTheDocument();
  });

  it("recomputes pending and expired token states on manual refresh", async () => {
    const { tokens, token } = await verifyWizard();
    tokens.mockResolvedValue({ tokens: [{ ...token, consumed_at: null, consumed_by_host_id: null, expires_at: new Date(Date.now() - 1000).toISOString() }], count: 1 });
    fireEvent.click(screen.getByRole("button", { name: /refresh status/i }));
    expect(await screen.findByText("Bootstrap token expired")).toBeInTheDocument();
    expect(screen.queryByText("Consumed")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /continue to host/i })).toBeDisabled();
    tokens.mockResolvedValue({ tokens: [{ ...token, consumed_at: null, consumed_by_host_id: null }], count: 1 });
    fireEvent.click(screen.getByRole("button", { name: /refresh status/i }));
    await waitFor(() => expect(screen.queryByText("Bootstrap token expired")).not.toBeInTheDocument());
    expect(screen.getByText(/Waiting for agent enrollment/i)).toBeInTheDocument();
  });

  it("does not call a missing readiness probe ready when health is degraded", async () => {
    vi.spyOn(api, "health").mockResolvedValue({ status: "degraded", database: "degraded" } as any);
    vi.spyOn(api, "readiness").mockRejectedValue(new Error("offline"));
    wrap(<Settings />);
    const panel = await screen.findByTestId("readiness-degraded");
    expect(panel).toHaveTextContent("Readiness probe unavailable");
    expect(panel).not.toHaveTextContent("reports ready");
  });
});
