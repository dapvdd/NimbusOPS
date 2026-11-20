import { useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { api } from '../api/client';
import { useSession } from '../auth/Session';

export default function Login() {
  const session = useSession();
  const location = useLocation();
  const [username,setUsername] = useState('');
  const [password,setPassword] = useState('');
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const from = location.state?.from;
  if (session?.user) return <Navigate to={typeof from === 'string' && from.startsWith('/') && !from.startsWith('//') && from !== '/login' ? from : '/'} replace />;
  return <main className="min-h-screen grid place-items-center bg-ink-950 px-6"><section className="w-full max-w-md rounded-xl border border-ink-700 bg-ink-900 p-8 shadow-xl">
    <p className="text-xs uppercase tracking-widest text-signal-info">NimbusOps · Infrastructure console</p>
    <h1 className="mt-4 text-2xl font-semibold">Sign in to NimbusOps</h1>
    <p className="mt-2 text-sm text-ink-300">Use your operator account. Viewer accounts have read-only access.</p>
    <form className="mt-6 space-y-4" onSubmit={async e => {e.preventDefault();setBusy(true);setError('');try {await api.browserLogin(username,password);setPassword('');await session?.reload();} catch(e) {setError(e instanceof Error?e.message:'Sign-in failed.');setPassword('');} finally {setBusy(false);} }}>
      <label className="block text-sm">Username<input required autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} className="mt-2 w-full rounded border border-ink-600 bg-ink-950 p-3" /></label>
      <label className="block text-sm">Password<input required type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} className="mt-2 w-full rounded border border-ink-600 bg-ink-950 p-3" /></label>
      {(error || session?.error) && <p role="alert" className="text-sm text-signal-bad">{error || session?.error}</p>}
      <button disabled={busy || session?.loading} className="w-full rounded bg-signal-info p-3 font-semibold text-ink-950 disabled:opacity-50">{busy?'Signing in…':'Sign in'}</button>
    </form>
  </section></main>;
}
