import { afterEach, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import Activity from "../Activity";

// Task 8: Activity reads the real operation history API (FR-08); the former
// applications-based mock is replaced by the operations contract.
afterEach(() => vi.unstubAllGlobals());

it("filters history to the selected real host", async () => {
  const fetchMock = vi.fn().mockImplementation((url: RequestInfo | URL) => {
    const target = String(url);
    if (target.includes("/operations")) {
      const hostFiltered = target.includes("host_id=a");
      return Promise.resolve({ ok: true, json: async () => ({
        operations: hostFiltered ? [
          { id: "op1", deployment_id: "1", host_id: "a", op_type: "DEPLOY", status: "SUCCEEDED", created_at: "2026-11-09T00:00:00Z", updated_at: "2026-11-09T00:00:00Z", completed_at: null, result: null, error_code: null, error_message: null },
        ] : [
          { id: "op1", deployment_id: "1", host_id: "a", op_type: "DEPLOY", status: "SUCCEEDED", created_at: "2026-11-09T00:00:00Z", updated_at: "2026-11-09T00:00:00Z", completed_at: null, result: null, error_code: null, error_message: null },
          { id: "op2", deployment_id: "2", host_id: "b", op_type: "STOP", status: "FAILED", created_at: "2026-11-09T00:00:00Z", updated_at: "2026-11-09T00:00:00Z", completed_at: null, result: null, error_code: null, error_message: null },
        ],
        count: hostFiltered ? 1 : 2,
      }) });
    }
    return Promise.resolve({ ok: true, json: async () => ({}) });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<Activity hostId="a" />);
  expect(await screen.findByText("op1")).toBeInTheDocument();
  // The view must have requested only host a's operations.
  expect(fetchMock.mock.calls.some(c => String(c[0]).includes("host_id=a"))).toBe(true);
  expect(screen.queryByText("op2")).not.toBeInTheDocument();
});
