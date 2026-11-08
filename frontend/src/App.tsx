import { Navigate, Route, Routes } from "react-router-dom";
import Overview from "./views/Overview";
import HostDetail from "./views/HostDetail";
import { AppShell } from "./components/AppShell";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/hosts/:hostId" element={<HostDetail />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
