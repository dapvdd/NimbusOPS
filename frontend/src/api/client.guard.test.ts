import { afterEach, expect, it, vi } from "vitest";
import { api } from "./client";
afterEach(() => vi.unstubAllGlobals());
it("blocks simulated IDs at every host and operation API boundary", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  for (const call of [() => api.deploy("sim-abc", "nginx-demo"), () => api.startApp("sim-abc"), () => api.stopApp("sim-abc"), () => api.getHost("sim-abc"), () => api.getHostMetrics("sim-abc"), () => api.getOperation("sim-abc"), () => api.getContainerState("sim-abc")]) {
    await expect(call()).rejects.toThrow(/simulated/i);
  }
  expect(fetch).not.toHaveBeenCalled();
});
