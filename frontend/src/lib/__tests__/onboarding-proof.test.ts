import { expect, it } from "vitest";
import type { BootstrapTokenInfo, Host } from "../../api/types";
import { enrollmentProof } from "../onboarding";

const now = Date.parse("2026-11-20T10:00:00Z");
const token = {
  consumed_at: "2026-11-20T09:59:00Z", consumed_by_host_id: "new-host",
} as BootstrapTokenInfo;
const host = {
  id: "new-host", hostname: "node.example", status: "ONLINE", is_revoked: false,
  enrollment_status: "ENROLLED", last_seen_at: "2026-11-20T09:59:30Z",
  last_telemetry_at: "2026-11-20T09:59:30Z",
  latest_metrics: { recorded_at: "2026-11-20T09:59:30Z" },
} as Host;

it("binds registration to consumed host id rather than hostname", () => {
  expect(enrollmentProof(token, [{ ...host, id: "old-host" }], now).host).toBeNull();
  expect(enrollmentProof({ ...token, consumed_at: null }, [host], now).host).toBeNull();
  expect(enrollmentProof(token, [host], now).host?.id).toBe("new-host");
});

it("requires online heartbeat and telemetry after this consumption", () => {
  expect(enrollmentProof(token, [host], now).ready).toBe(true);
  for (const patch of [
    { last_seen_at: "2026-11-20T09:58:00Z" },
    { last_telemetry_at: "2026-11-20T09:58:00Z" },
    { latest_metrics: { ...host.latest_metrics!, recorded_at: "2026-11-20T09:58:00Z" } },
    { status: "STALE" as const }, { is_revoked: true },
    { last_seen_at: "2026-11-20T11:00:00Z" },
  ]) {
    expect(enrollmentProof(token, [{ ...host, ...patch }], now).ready).toBe(false);
  }
  expect(enrollmentProof(token, [host], now + 600_000).ready).toBe(false);
});

it("interprets offsetless SQLite wire timestamps as UTC", () => {
  const naiveHost = { ...host,
    last_seen_at: "2026-11-20T09:59:30",
    last_telemetry_at: "2026-11-20T09:59:30",
    latest_metrics: { ...host.latest_metrics!, recorded_at: "2026-11-20T09:59:30" },
  };
  expect(enrollmentProof({ ...token, consumed_at: "2026-11-20T09:59:00" }, [naiveHost], now).ready).toBe(true);
});
