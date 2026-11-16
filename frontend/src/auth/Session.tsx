import { createContext, useContext, useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { api, ApiFailure, refreshCsrf } from '../api/client';
import type { MeResponse } from '../api/types';

type Session = { user: MeResponse | null; loading: boolean; error: string; reload: () => Promise<void>; logout: () => Promise<void> };
const Context = createContext<Session | null>(null);

export function useSession() { return useContext(Context); }
export function useAdmin() { return useSession()?.user?.role === 'ADMIN'; }

export function SessionProvider({children}: {children: React.ReactNode}) {
  const [user,setUser] = useState<MeResponse | null>(null);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState('');
  const reload = async () => {
    setError('');
    try { const me = await api.me(); await refreshCsrf(); setUser(me); }
    catch(e) { setUser(null); if (!(e instanceof ApiFailure && e.status === 401)) setError('Cannot verify your session. Check the API and try again.'); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    void reload();
    const expired = () => { setUser(null); setError('Your session expired. Please sign in again.'); };
    window.addEventListener('nimbusops:session-expired',expired);
    return () => window.removeEventListener('nimbusops:session-expired',expired);
  },[]);
  const logout = async () => { await api.browserLogout(); setUser(null); setError(''); };
  return <Context.Provider value={{user,loading,error,reload,logout}}>{children}</Context.Provider>;
}

export function Protected({children}: {children: React.ReactNode}) {
  const session = useSession();
  const location = useLocation();
  if (session?.loading) return <p role="status" className="p-8">Checking session…</p>;
  if (!session?.user) return <Navigate to="/login" replace state={{from:location.pathname}} />;
  return <>{children}</>;
}
