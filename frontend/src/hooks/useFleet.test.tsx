import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { useFleet } from "./useFleet";

const session = vi.hoisted(() => ({ admin: false }));
vi.mock("../auth/Session", () => ({ useAdmin: () => session.admin }));
afterEach(() => { vi.restoreAllMocks(); session.admin = false; });

describe("useFleet token permissions", () => {
  it("does not request admin tokens for viewers on load, retry, or poll", async () => {
    const interval = vi.spyOn(globalThis, "setInterval");
    vi.spyOn(api, "listHosts").mockResolvedValue({ hosts: [], count: 0 });
    const tokens = vi.spyOn(api, "listBootstrapTokens").mockRejectedValue(new Error("403 forbidden"));
    const { result } = renderHook(() => useFleet());
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => { await result.current.refetch(); });
    const poll = interval.mock.calls.find(([, delay]) => delay === 5000)![0] as () => void;
    await act(async () => { poll(); });
    expect(tokens).not.toHaveBeenCalled();
    expect(result.current.tokens).toEqual([]);
    expect(result.current.tokensError).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.tokensAccess).toBe("denied");
  });

  it("retains unavailable-feed errors for authorized admins", async () => {
    session.admin = true;
    vi.spyOn(api, "listHosts").mockResolvedValue({ hosts: [], count: 0 });
    vi.spyOn(api, "listBootstrapTokens").mockRejectedValue(new Error("token service offline"));
    const { result } = renderHook(() => useFleet());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.tokensError?.message).toBe("token service offline");
    expect(result.current.tokensAccess).toBe("allowed");
    expect(result.current.error).toBeNull();
  });
});
