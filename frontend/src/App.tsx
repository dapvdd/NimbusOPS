import { Navigate, Route, Routes } from "react-router-dom";
import Overview from "./views/Overview";
import Applications from "./views/Applications";
import { AppShell } from "./components/AppShell";
import Servers from "./views/Servers";
import ServerDetail from "./views/ServerDetail";
import Activity from "./views/Activity";
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
        <Route path="/hosts/:hostId" element={<ServerDetail />} />
        <Route path="/servers" element={<Servers />} />
        <Route path="/servers/:hostId" element={<ServerDetail />} />
        <Route path="/deployments" element={<Applications />} />
        <Route path="/activity" element={<Activity />} />
        <Route path="/settings" element={<div><h1 className="text-3xl">Settings</h1><p className="mt-4">Real host enrollment uses an operator-issued, single-use bootstrap token; credential rotation and revocation are available from the host views. Simulated identities and their history are stored only in this browser.</p></div>} />
        <Route path="/applications" element={<Applications />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
