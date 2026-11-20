import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { api } from "../api/client";
import type { HealthResponse } from "../api/types";
import { formatUtcTime } from "../lib/format";
import { Sidebar } from "./Sidebar";
import { useSession } from '../auth/Session';

/**
 * Top bar with brand, health indicator, and primary navigation. Health is
 * polled so "API unavailable" is honest and immediate, not assumed.
 */

type ConnState = "checking" | "ok" | "degraded" | "down";

function HealthDot({ state }: { state: ConnState }) {
  if (state === "ok") {
    return <span className="inline-block h-2 w-2 rounded-full bg-signal-ok" aria-label="API online" />;
  }
  if (state === "degraded") {
    return <span className="inline-block h-2 w-2 rounded-full bg-signal-warn" aria-label="API degraded" />;
  }
  if (state === "down") {
    return <span className="inline-block h-2 w-2 rounded-full bg-signal-bad" aria-label="API unreachable" />;
  }
  return <span className="inline-block h-2 w-2 rounded-full bg-ink-400 animate-pulse" aria-label="Checking API" />;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const session = useSession();
  const [logoutError,setLogoutError] = useState('');
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [conn, setConn] = useState<ConnState>("checking");

  useEffect(() => {
    let alive = true;
    const check = async () => {
      try {
        const h = await api.health();
        if (!alive) return;
        setHealth(h);
        // RC2 F12: "reachable" is not "healthy". A degraded dependency keeps
        // the shell honest instead of showing a green dot.
        setConn(h.status === "ok" ? "ok" : "degraded");
      } catch {
        if (!alive) return;
        setHealth(null);
        setConn("down");
      }
    };
    check();
    const id = window.setInterval(check, 10_000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  return (
    <div className="console-layout">
      <Sidebar />
      <div className="min-w-0 flex min-h-screen flex-col">
      <header className="border-b border-ink-700 bg-ink-900/80 backdrop-blur sticky top-0 z-10">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 h-14 flex items-center gap-6">
          <NavLink to="/" className="flex items-center gap-2.5 shrink-0">
            <span className="grid h-7 w-7 place-items-center rounded bg-signal-info/15 text-signal-info font-bold text-sm">
              N
            </span>
            <span className="font-semibold tracking-tight text-ink-100">NimbusOps</span>
            <span className="hidden sm:inline text-[11px] uppercase tracking-widest text-ink-400 border border-ink-600 rounded px-1.5 py-0.5">
              RC2
            </span>
          </NavLink>
          <nav className="hidden">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-md transition-colors ${
                  isActive ? "bg-ink-700 text-ink-100" : "text-ink-300 hover:text-ink-100 hover:bg-ink-800"
                }`
              }
            >
              Overview
            </NavLink>
            <NavLink
              to="/applications"
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-md transition-colors ${
                  isActive ? "bg-ink-700 text-ink-100" : "text-ink-300 hover:text-ink-100 hover:bg-ink-800"
                }`
              }
            >
              Applications
            </NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-4 text-xs text-ink-300">
            {session?.user && <><span>{session.user.username} · {session.user.role}</span><button onClick={() => { void session.logout().catch(()=>setLogoutError('Logout failed. Please retry.')); }}>Log out</button>{logoutError && <span role="alert">{logoutError}</span>}</>}
            {conn === "ok" && health ? (
              <span className="flex items-center gap-2">
                <HealthDot state={conn} />
                <span className="hidden sm:inline" title={`build ${health.build}`}>
                  v{health.version} · {health.build}
                </span>
              </span>
            ) : conn === "degraded" && health ? (
              <span className="flex items-center gap-2 text-signal-warn">
                <HealthDot state={conn} />
                <span>
                  API degraded
                  {health.database !== "ok" ? " (database)" : ""}
                </span>
              </span>
            ) : (
              <span className="flex items-center gap-2 text-signal-bad">
                <HealthDot state={conn} />
                <span>{conn === "down" ? "API unavailable" : "Checking API…"}</span>
              </span>
            )}
            {health && (
              <span className="hidden md:inline font-mono text-[11px] text-ink-400" title="Server time (UTC)">
                {formatUtcTime(health.server_time)}
              </span>
            )}
          </div>
        </div>
      </header>
      <main className="flex-1 mx-auto w-full max-w-7xl px-4 sm:px-6 py-6">{children}</main>
      <footer className="border-t border-ink-800 text-xs text-ink-400">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 h-10 flex items-center justify-between">
          <span>NimbusOps — infrastructure console</span>
          <span>Timestamps in UTC</span>
        </div>
      </footer>
      </div>
    </div>
  );
}
