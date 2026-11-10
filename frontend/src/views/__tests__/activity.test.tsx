import { afterEach, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import Activity from "../Activity";
afterEach(() => vi.unstubAllGlobals());
it("filters latest operations to the selected real host", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ applications: [
    { host_id: "a", deployment_id: "1", container_name: "selected-app", last_operation: { id: "op1", op_type: "DEPLOY", status: "SUCCEEDED", updated_at: "2026-11-09T00:00:00Z" } },
    { host_id: "b", deployment_id: "2", container_name: "other-app", last_operation: { id: "op2", op_type: "STOP", status: "FAILED", updated_at: "2026-11-09T00:00:00Z" } }
  ] }) }));
  render(<Activity hostId="a" />);
  expect(await screen.findByText("selected-app")).toBeInTheDocument();
  expect(screen.queryByText("other-app")).not.toBeInTheDocument();
});
