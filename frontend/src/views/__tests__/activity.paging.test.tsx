import { afterEach, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import Activity from "../Activity";

// RC2 F10: the status filter must run on the server and history must be
// reachable beyond the first window via offset paging.

const op = (id: string, status: string, createdAt: string) => ({
  id,
  deployment_id: "dep-1",
  host_id: "h-1",
  op_type: "DEPLOY",
  status,
  created_at: createdAt,
  updated_at: createdAt,
  completed_at: null,
  result: null,
  error_code: null,
  error_message: null,
});

afterEach(() => vi.unstubAllGlobals());

it("restores pagination after switching filters during an older-page request", async () => {
  let resolveOlder!: (value: unknown) => void;
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => {
    if (String(url).includes('offset=1') && !String(url).includes('status=')) return new Promise(resolve => {resolveOlder = resolve;});
    return Promise.resolve({ok: true, json: async () => ({operations: [op('new-filter', 'FAILED', '2026-11-12T09:00:00Z')], total: 2})});
  }));
  render(<Activity />);
  fireEvent.click(await screen.findByRole('button', {name: /load older/i}));
  fireEvent.click(screen.getByRole('button', {name: 'FAILED'}));
  await act(async () => resolveOlder({ok: true, json: async () => ({operations: [], total: 2})}));
  expect(await screen.findByRole('button', {name: /load older/i})).toBeEnabled();
});

it("ignores a late response from an obsolete status filter", async () => {
  let resolveOld!: (value: unknown) => void;
  vi.stubGlobal("fetch", vi.fn((url: RequestInfo | URL) => {
    if (!String(url).includes("status=FAILED")) return new Promise(resolve => { resolveOld = resolve; });
    return Promise.resolve({ ok: true, json: async () => ({operations: [op("current-failed", "FAILED", "2026-11-12T09:00:00Z")], total: 1}) });
  }));
  render(<Activity />);
  fireEvent.click(screen.getByRole("button", { name: "FAILED" }));
  await screen.findByText("current-failed");
  await act(async () => resolveOld({ok: true, json: async () => ({operations: [op("obsolete-success", "SUCCEEDED", "2026-11-12T09:00:00Z")], total: 1})}));
  expect(screen.queryByText("obsolete-success")).not.toBeInTheDocument();
  expect(screen.getByText("current-failed")).toBeInTheDocument();
});

it("sends the status filter to the server and pages older rows by offset", async () => {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: RequestInfo | URL) => {
      const target = String(url);
      calls.push(target);
      const body = target.includes("offset=1")
        ? { operations: [op("op-old", "FAILED", "2026-11-12T08:00:00Z")], count: 1, total: 2, offset: 1 }
        : { operations: [op("op-new", "FAILED", "2026-11-12T09:00:00Z")], count: 1, total: 2, offset: 0 };
      return Promise.resolve({ ok: true, json: async () => body });
    }),
  );
  render(<Activity />);

  await screen.findByText("op-new");
  fireEvent.click(screen.getByRole("button", { name: "FAILED" }));

  await waitFor(() => expect(calls.some((c) => c.includes("status=FAILED"))).toBe(true));

  fireEvent.click(await screen.findByRole("button", { name: /load older/i }));
  expect(await screen.findByText("op-old")).toBeInTheDocument();
  // Both rows stay visible: paging appends, it does not replace.
  expect(screen.getByText("op-new")).toBeInTheDocument();
  expect(calls.some((c) => c.includes("offset=1"))).toBe(true);
});

it("states that the list is newest-first and shows the history size", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        operations: [op("op-new", "SUCCEEDED", "2026-11-12T09:00:00Z")],
        count: 1,
        total: 40,
        offset: 0,
      }),
    }),
  );
  render(<Activity />);
  await screen.findByText("op-new");
  expect(screen.getByText(/newest first/i)).toBeInTheDocument();
  expect(screen.getByText(/1 of 40/i)).toBeInTheDocument();
});
