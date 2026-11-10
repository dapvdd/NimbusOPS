import { useState } from "react";
import { NavLink } from "react-router-dom";
import { ServerList } from "./ServerList";
const links = [["/", "Overview"], ["/servers", "Servers"], ["/deployments", "Deployments"], ["/activity", "Activity"], ["/settings", "Settings"]];
export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  return <aside className={`console-sidebar ${collapsed ? "is-collapsed" : ""}`}><NavLink to="/" className="flex items-center gap-3 px-3 py-5 text-xl font-semibold"><span className="rounded-lg bg-signal-info/20 p-2 text-signal-info">N</span>{!collapsed && "NimbusOps"}</NavLink><button className="mb-8 px-3 text-xs text-ink-300" aria-expanded={!collapsed} onClick={() => setCollapsed(v => !v)}>{collapsed ? "Expand" : "Collapse sidebar"}</button><nav aria-label="Primary" className="space-y-2">{links.map(([path, label], i) => <NavLink key={path} to={path} end={path === "/"} title={label} aria-label={label} className={({ isActive }) => `flex items-center gap-3 rounded-lg px-4 py-3 text-sm ${isActive ? "bg-signal-info/15 text-signal-info" : "text-ink-300 hover:bg-ink-800"}`}><svg aria-hidden="true" width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="14" height="14" rx={i === 4 ? 7 : 3}/><path d={i === 2 ? "M7 6l6 4-6 4Z" : "M6 8h8M6 12h5"}/></svg>{!collapsed && label}</NavLink>)}{!collapsed && <ServerList />}</nav><div className="mt-auto px-3 py-6 text-xs text-ink-400">{collapsed ? "3A" : "Infrastructure console · Phase 3A"}</div></aside>;
}
