import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Servers from "../Servers";
vi.mock('../../auth/Session', () => ({ useAdmin: () => true, useSession: () => null }));
beforeEach(() => { localStorage.clear(); vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ hosts: [], count: 0 }) })); });
afterEach(() => vi.unstubAllGlobals());
it("keeps local simulations usable when the API fails", async () => {
  vi.mocked(fetch).mockRejectedValue(new Error("offline"));
  render(<MemoryRouter><Servers /></MemoryRouter>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Real infrastructure unavailable");
  fireEvent.change(screen.getByLabelText("Search servers"), { target: { value: "missing" } });
  expect(screen.getByText("No servers match your search.")).toBeInTheDocument();
});
it("adds and removes a clearly labeled simulation without mutation requests", async () => {
  render(<MemoryRouter><Servers /></MemoryRouter>);
  await screen.findByText("No real servers registered");
  fireEvent.click(screen.getByText("Add Server"));
  fireEvent.change(screen.getByLabelText("Server name"), { target: { value: "demo-edge" } });
  fireEvent.click(screen.getByText("Create simulated server"));
  expect(screen.getByText("demo-edge")).toBeInTheDocument();
  expect(screen.getAllByText(/SIMULATED/).length).toBeGreaterThan(0);
  fireEvent.click(screen.getByLabelText("Remove demo-edge"));
  fireEvent.click(screen.getByText("Confirm removal"));
  expect(screen.queryByText("demo-edge")).not.toBeInTheDocument();
  expect(vi.mocked(fetch).mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
});
it("existing-server enrollment links to onboarding wizard", async () => {
  render(<MemoryRouter><Servers /></MemoryRouter>);
  await screen.findByText("No real servers registered");
  fireEvent.click(screen.getByText("Add Server"));
  fireEvent.click(screen.getByText("Existing server"));
  expect(screen.getByText("Start Enrollment")).toBeInTheDocument();
});
