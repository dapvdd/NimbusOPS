import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Host } from "../api/types";

interface Item {
  id: string;
  name: string;
  status: Host["status"];
  environment: string;
}

/** Host-aware server list inside the sidebar: real hosts from the API only. */
export function ServerList() {
  const { hostId: selectedId } = useParams();
  const [real, setReal] = useState<Host[]>([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .listHosts()
        .then((data) => {
          if (alive) setReal(data?.hosts ?? []);
        })
        .catch(() => {
          // Sidebar list is supplementary; Servers page reports the failure.
        });
    load();
    const timer = window.setInterval(load, 30_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const items = useMemo<Item[]>(
    () =>
      real.map((h) => ({
        id: h.id,
        name: h.hostname,
        status: h.is_revoked || h.enrollment_status === "REVOKED" ? "REVOKED" : h.status,
        environment: "REAL",
      })),
    [real],
  );

  const filtered = items.filter((i) =>
    i.name.toLowerCase().includes(query.trim().toLowerCase()),
  );

  return (
    <div className="mt-2">
      <label className="block px-3 text-[11px] uppercase tracking-widest text-ink-400">
        Servers
        <input
          aria-label="Search servers"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter…"
          className="mt-2 w-full rounded-md border border-ink-700 bg-ink-900 px-2 py-1.5 text-xs text-ink-100 placeholder:text-ink-500"
        />
      </label>
      <ul className="mt-3 space-y-1">
        {filtered.map((item) => (
          <li key={item.id}>
            <Link
              to={`/servers/${item.id}`}
              className={`flex items-center gap-2 rounded-md px-3 py-2 text-xs ${
                selectedId === item.id
                  ? "bg-ink-700 text-ink-100"
                  : "text-ink-300 hover:bg-ink-800"
              }`}
            >
              <span
                aria-hidden="true"
                className={`h-2 w-2 shrink-0 rounded-full ${
                  item.status === "ONLINE"
                    ? "bg-signal-ok"
                    : item.status === "STALE"
                      ? "bg-signal-warn"
                      : item.status === "REVOKED"
                        ? "bg-purple-400"
                        : "bg-signal-bad"
                }`}
              />
              <span className="truncate">{item.name}</span>
              <span className="ml-auto shrink-0 rounded border border-ink-600 px-1 py-0.5 text-[9px] uppercase tracking-wide text-ink-400">
                {item.environment}
              </span>
            </Link>
          </li>
        ))}
        {filtered.length === 0 && (
          <li className="px-3 py-2 text-xs text-ink-500">No servers match.</li>
        )}
      </ul>
    </div>
  );
}
