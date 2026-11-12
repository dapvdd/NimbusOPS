import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Activity from "../Activity";

const historyPayload = {
  operations: [
    { id: "op-1", deployment_id: "dep-1", host_id: "h-1", op_type: "DEPLOY",
      status: "SUCCEEDED", created_at: "2026-11-12T09:00:00Z",
      updated_at: "2026-11-12T09:01:00Z", completed_at: "2026-11-12T09:01:00Z",
      result: null, error_code: null, error_message: null },
    { id: "op-2", deployment_id: "dep-1", host_id: "h-1", op_type: "RESTART",
      status: "FAILED", created_at: "2026-11-12T09:05:00Z",
      updated_at: "2026-11-12T09:06:00Z", completed_at: "2026-11-12T09:06:00Z",
      result: null, error_code: "DOCKER_FAILURE", error_message: "restart failed" },
    { id: "op-3", deployment_id: "dep-2", host_id: "h-2", op_type: "STOP",
      status: "QUEUED", created_at: "2026-11-12T09:10:00Z",
      updated_at: "2026-11-12T09:10:00Z", completed_at: null,
      result: null, error_code: null, error_message: null },
  ],
  count: 3,
};

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => vi.unstubAllGlobals());

it("renders real operation history from the API", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => historyPayload }));
  render(<MemoryRouter><Activity /></MemoryRouter>);
  expect(await screen.findByText("op-1")).toBeInTheDocument();
  expect(screen.getByText("op-2")).toBeInTheDocument();
  expect(screen.getByText("op-3")).toBeInTheDocument();
  expect(screen.getByText(/DOCKER_FAILURE/)).toBeInTheDocument();
});

it("filters by status", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => historyPayload }));
  render(<MemoryRouter><Activity /></MemoryRouter>);
  await screen.findByText("op-1");
  fireEvent.click(screen.getByRole("button", { name: "FAILED" }));
  expect(screen.queryByText("op-1")).not.toBeInTheDocument();
  expect(screen.getByText("op-2")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "ALL" }));
  expect(screen.getByText("op-1")).toBeInTheDocument();
});

it("shows empty state when no operations exist", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ operations: [], count: 0 }) }));
  render(<MemoryRouter><Activity /></MemoryRouter>);
  expect(await screen.findByText(/no operations recorded/i)).toBeInTheDocument();
});

it("shows error state with retry on API failure", async () => {
  const failing = vi.fn()
    .mockRejectedValueOnce(new Error("control server unreachable"));
  vi.stubGlobal("fetch", failing);
  render(<MemoryRouter><Activity /></MemoryRouter>);
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  failing.mockResolvedValue({ ok: true, json: async () => historyPayload });
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  expect(await screen.findByText("op-1")).toBeInTheDocument();
});
