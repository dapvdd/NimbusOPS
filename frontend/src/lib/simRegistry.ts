export type SimEnvironment = "SIMULATED-DEV" | "SIMULATED-STAGING" | "SIMULATED-PROD";
export interface SimServer { id: string; name: string; environment: SimEnvironment; seed: number; created_at: string }
export interface SimRemovedEntry { id: string; name: string; removed_at: string }
interface Registry { servers: SimServer[]; removed: SimRemovedEntry[] }
const KEY = "nimbusops.sim-registry.v1";
export const isSimulatedHostId = (id: string) => id.startsWith("sim-");
function read(): Registry {
  try {
    const data = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (!data || !Array.isArray(data.servers) || !Array.isArray(data.removed)) return { servers: [], removed: [] };
    // Deduplicate by ID: React keys and removal must address exactly one host.
    const seen = new Set<string>();
    const unique = <T extends { id: string }>(entries: T[], valid: (entry: T) => boolean) =>
      entries.filter((entry) => {
        if (!valid(entry) || seen.has(entry.id)) return false;
        seen.add(entry.id);
        return true;
      });
    const servers = unique<SimServer>(data.servers, (s) =>
      typeof s.id === "string" &&
      isSimulatedHostId(s.id) &&
      typeof s.name === "string" &&
      Number.isFinite(s.seed) &&
      ["SIMULATED-DEV", "SIMULATED-STAGING", "SIMULATED-PROD"].includes(s.environment),
    );
    seen.clear();
    const removed = unique<SimRemovedEntry>(data.removed, (s) =>
      typeof s.id === "string" &&
      isSimulatedHostId(s.id) && typeof s.name === "string" && typeof s.removed_at === "string",
    );
    return { servers, removed };
  } catch { return { servers: [], removed: [] }; }
}
function save(data: Registry) {
  localStorage.setItem(KEY, JSON.stringify(data));
  window.dispatchEvent(new Event("nimbusops:registry"));
}
export const listSimServers = () => read().servers;
export const listRemovedServers = () => read().removed;
export function addSimServer(name: string, environment: SimEnvironment): SimServer {
  name = name.trim();
  if (!name || name.length > 64) throw new Error("Name must contain 1–64 characters.");
  if (!["SIMULATED-DEV", "SIMULATED-STAGING", "SIMULATED-PROD"].includes(environment)) throw new Error("Invalid simulation environment.");
  const data = read();
  if (data.servers.some(s => s.name.toLowerCase() === name.toLowerCase())) throw new Error("A simulated server with this name already exists.");
  const host = { id: `sim-${crypto.randomUUID()}`, name, environment, seed: Date.now() % 10000, created_at: new Date().toISOString() };
  save({ ...data, servers: [...data.servers, host] });
  return host;
}
export function removeSimServer(id: string): void {
  if (!isSimulatedHostId(id)) throw new Error("Real server removal is not implemented.");
  const data = read();
  const host = data.servers.find(s => s.id === id);
  if (!host) return;
  save({ servers: data.servers.filter(s => s.id !== id), removed: [...data.removed, { id, name: host.name, removed_at: new Date().toISOString() }] });
}
