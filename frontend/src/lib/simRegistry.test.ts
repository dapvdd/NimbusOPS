import { beforeEach, expect, it } from "vitest";
import { addSimServer, listSimServers, removeSimServer, listRemovedServers } from "./simRegistry";
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
it("handles corrupt data and refuses real host removal", () => {
  localStorage.setItem("nimbusops.sim-registry.v1", "invalid");
  expect(listSimServers()).toEqual([]);
  expect(() => removeSimServer("real-host")).toThrow();
});
