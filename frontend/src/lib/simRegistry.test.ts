import { beforeEach, expect, it } from "vitest";
import {
  addSimServer,
  listRemovedServers,
  listSimServers,
  removeSimServer,
} from "./simRegistry";

const KEY = "nimbusops.sim-registry.v1";
const valid = {
  id: "sim-11111111-1111-4111-8111-111111111111",
  name: "edge-demo",
  environment: "SIMULATED-DEV",
  seed: 42,
  created_at: "2026-11-10T06:00:00.000Z",
};

beforeEach(() => localStorage.clear());

it("persists simulation identity and removal history", () => {
  const host = addSimServer(" demo-web ", "SIMULATED-DEV");
  expect(host.id).toMatch(/^sim-/);
  expect(listSimServers()[0]).toEqual(host);
  expect(host.name).toBe("demo-web");
  removeSimServer(host.id);
  expect(listSimServers()).toEqual([]);
  expect(listRemovedServers()[0].id).toBe(host.id);
});

it("rejects invalid and duplicate names", () => {
  expect(() => addSimServer(" ", "SIMULATED-DEV")).toThrow();
  expect(() => addSimServer("x".repeat(65), "SIMULATED-DEV")).toThrow();
  addSimServer("Demo", "SIMULATED-DEV");
  expect(() => addSimServer("demo", "SIMULATED-DEV")).toThrow();
});

it("handles corrupt stored data and refuses real host removal", () => {
  localStorage.setItem(KEY, "invalid");
  expect(listSimServers()).toEqual([]);
  expect(() => removeSimServer("real-host")).toThrow();
});

it("deduplicates stored IDs so removal is unambiguous", () => {
  localStorage.setItem(
    KEY,
    JSON.stringify({
      servers: [valid, { ...valid, name: "duplicate-copy" }, { ...valid, id: "real-host" }],
      removed: [],
    }),
  );
  expect(listSimServers()).toEqual([valid]);
});

it("keeps only valid entries from a tampered registry", () => {
  localStorage.setItem(
    KEY,
    JSON.stringify({
      servers: [
        valid,
        { ...valid, id: "sim-2", name: 42 },
        { ...valid, id: "sim-3", environment: "PRODUCTION" },
        { ...valid, id: "sim-4", seed: null },
      ],
      removed: [{ id: "sim-5", name: "gone", removed_at: "not-a-date" }, { id: "sim-6" }],
    }),
  );
  expect(listSimServers()).toEqual([valid]);
  expect(listRemovedServers()).toHaveLength(1);
});

it("does not resurrect a removed server from a duplicate entry", () => {
  localStorage.setItem(
    KEY,
    JSON.stringify({ servers: [valid, { ...valid, name: "duplicate-copy" }], removed: [] }),
  );
  removeSimServer(valid.id);
  expect(listSimServers()).toEqual([]);
  expect(listRemovedServers()).toHaveLength(1);
});
