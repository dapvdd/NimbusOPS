import { afterEach, expect, it, vi } from "vitest";
import { api } from "./client";

afterEach(() => vi.unstubAllGlobals());

function stubFetch() {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

it("blocks simulated IDs at every host and operation API boundary", async () => {
  const fetch = stubFetch();
  for (const call of [
    () => api.deploy("sim-abc", "nginx-demo"),
    () => api.startApp("sim-abc"),
    () => api.stopApp("sim-abc"),
    () => api.getHost("sim-abc"),
    () => api.getHostMetrics("sim-abc"),
    () => api.getOperation("sim-abc"),
    () => api.getContainerState("sim-abc"),
  ]) {
    await expect(call()).rejects.toThrow(/simulated/i);
  }
  expect(fetch).not.toHaveBeenCalled();
});

it("normalises case and percent-encoding before deciding", async () => {
  const fetch = stubFetch();
  await expect(api.getHost("SIM-abc")).rejects.toThrow(/simulated/i);
  await expect(api.startApp("SIM-abc")).rejects.toThrow(/simulated/i);
  // deploy sends host_id in the JSON body; encoded bodies must not bypass the guard.
  await expect(api.deploy("sim%2Dabc", "nginx-demo")).rejects.toThrow(/simulated/i);
  await expect(api.deploy("SIM-abc", "nginx-demo")).rejects.toThrow(/simulated/i);
  expect(fetch).not.toHaveBeenCalled();
});

it("rejects malformed identifiers instead of crashing", async () => {
  const fetch = stubFetch();
  await expect(api.deploy("%E0%A4%A", "nginx-demo")).rejects.toThrow(/invalid resource/i);
  expect(fetch).not.toHaveBeenCalled();
});
