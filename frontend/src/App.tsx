import { Navigate, Route, Routes, useParams } from "react-router-dom";
import Overview from "./views/Overview";
import Applications from "./views/Applications";
import { AppShell } from "./components/AppShell";
import Servers from "./views/Servers";
import ServerDetail from "./views/ServerDetail";
import Onboarding from "./views/Onboarding";
import Activity from "./views/Activity";
import Settings from "./views/Settings";
import { Protected, SessionProvider } from './auth/Session';
import Login from './views/Login';

export default function App() {
  return <SessionProvider><Routes><Route path="/login" element={<Login />} /><Route path="*" element={<Protected><Console /></Protected>} /></Routes></SessionProvider>;
}

function Console() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/hosts/:hostId" element={<LegacyHostRedirect />} />
        <Route path="/servers" element={<Servers />} />
        <Route path="/servers/new" element={<Protected requireRole="ADMIN"><Onboarding /></Protected>} />
        <Route path="/servers/:hostId" element={<ServerDetail />} />
        <Route path="/deployments" element={<Applications />} />
        <Route path="/activity" element={<Activity />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/applications" element={<Applications />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}

/** One canonical host URL: keep old bookmarks working. */
function LegacyHostRedirect() {
  const { hostId = "" } = useParams();
  return <Navigate to={`/servers/${encodeURIComponent(hostId)}`} replace />;
}
