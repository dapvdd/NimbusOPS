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

it("extracts error code and message into ApiFailure", async () => {
  const fetch = stubFetch();
  fetch.mockResolvedValueOnce({
    ok: false,
    status: 409,
    json: async () => ({
      error: { code: "HOST_REVOKED", message: "revoked host" },
    }),
  });

  try {
    await api.getHost("valid-host-id");
    expect.unreachable("should have thrown ApiFailure");
  } catch (err: any) {
    expect(err.kind).toBe("http");
    expect(err.status).toBe(409);
    expect(err.code).toBe("HOST_REVOKED");
    expect(err.message).toBe("revoked host");
  }
});

it("readiness returns 503 as data and throws on network error", async () => {
  const fetch = stubFetch();

  // 503 response is treated as data, not thrown
  fetch.mockResolvedValueOnce({
    ok: false,
    status: 503,
    json: async () => ({
      ready: false,
      database: "degraded",
    }),
  });

  const res = await (api as any).readiness();
  expect(res.ready).toBe(false);
  expect(res.database).toBe("degraded");

  // Network error throws ApiFailure("network")
  fetch.mockRejectedValueOnce(new TypeError("Failed to fetch"));
  await expect((api as any).readiness()).rejects.toMatchObject({
    kind: "network",
  });
});

it("listHostEvents fetches /hosts/{id}/events with limit", async () => {
  const fetch = stubFetch();
  fetch.mockResolvedValueOnce({
    ok: true,
    json: async () => ({ events: [], count: 0 }),
  });

  await (api as any).listHostEvents("host-1", 50);
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/hosts/host-1/events?limit=50"),
    expect.anything()
  );
});

it("listBootstrapTokens appends active and limit query params when provided", async () => {
  const fetch = stubFetch();
  fetch.mockResolvedValueOnce({
    ok: true,
    json: async () => ({ tokens: [], count: 0 }),
  });

  await api.listBootstrapTokens({ active: true, limit: 25 });
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/operators/bootstrap-tokens?active=true&limit=25"),
    expect.anything()
  );

  fetch.mockResolvedValueOnce({
    ok: true,
    json: async () => ({ tokens: [], count: 0 }),
  });
  await api.listBootstrapTokens();
  expect(fetch).toHaveBeenCalledWith(
    "/api/v1/operators/bootstrap-tokens",
    expect.anything()
  );
});
