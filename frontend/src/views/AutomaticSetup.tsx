import { useEffect, useState } from 'react';
import { provisioning, type SetupJob, type SetupPlan } from '../api/provisioning';
import { Button } from '../ui/Button';
import { ApiFailure } from '../api/client';

interface ConfirmationIntent { key: string; plan: SetupPlan }
const intentStorage = 'nimbusops.setup.confirm.v1';

export default function AutomaticSetup() {
  const [targets, setTargets] = useState<{id: string; hostname: string; address: string}[]>([]);
  const [selected, setSelected] = useState('');
  const [plan, setPlan] = useState<SetupPlan | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [jobId, setJobId] = useState(() => {
    try { return sessionStorage.getItem('nimbusops.setup.job.v1') ?? ''; }
    catch { return ''; }
  });
  const [job, setJob] = useState<SetupJob | null>(null);
  const [intent, setIntent] = useState<ConfirmationIntent | null>(() => {
    try { return JSON.parse(sessionStorage.getItem(intentStorage) ?? 'null'); }
    catch { return null; }
  });
  const [missing, setMissing] = useState(false);
  const [rejected, setRejected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!intent || jobId) return;
    let active = true;
    provisioning.recover(intent.key).then(result => {
      if (active) acceptJob(result.id);
    }).catch(() => { if (active) setError('Confirmation outcome unavailable. Recover or resend the same confirmation; do not start another installation.'); });
    return () => { active = false; };
  }, [intent, jobId]);
  useEffect(() => {
    let active = true;
    provisioning.targets().then(data => { if (active) { setTargets(data.targets); setLoaded(true); } })
      .catch(() => { if (active) setError('Unable to load authorized targets.'); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!jobId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await provisioning.job(jobId);
        if (!active) return;
        setJob(next); setError('');
        if (!['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(next.state)) timer = setTimeout(poll, 3000);
      } catch (error) { if (active) {
        setError('Progress unavailable. Installation is not retried automatically.');
        if (error instanceof ApiFailure && [403, 404].includes(error.status ?? 0)) setMissing(true);
        else timer = setTimeout(poll, 5000);
      } }
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [jobId]);
  async function inspect() {
    setBusy(true); setError(''); setPlan(null); setConfirmed(false);
    try { setPlan(await provisioning.preflight(selected)); }
    catch { setError('Preflight rejected or unavailable. Check target authorization, SSH trust, OS and existing identity.'); }
    finally { setBusy(false); }
  }
  async function install() {
    if (!plan || !confirmed) return;
    setBusy(true); setError('');
    try {
      const pending = intent ?? {key: crypto.randomUUID(), plan};
      sessionStorage.setItem(intentStorage, JSON.stringify(pending));
      setIntent(pending);
      const result = await provisioning.confirm(pending.plan, pending.key);
      acceptJob(result.id);
    }
    catch { setError('Confirmation outcome unavailable or recovery storage blocked. Use the same confirmation to recover; do not start another installation.'); }
    finally { setBusy(false); }
  }
  function acceptJob(id: string) {
    setJobId(id); setMissing(false);
    try {
      sessionStorage.setItem('nimbusops.setup.job.v1', id);
      sessionStorage.removeItem(intentStorage);
      setIntent(null);
    } catch { /* Keep durable confirmation intent if storing job reference fails. */ }
  }
  async function recover() {
    if (!intent || busy) return;
    setBusy(true);
    try { acceptJob((await provisioning.confirm(intent.plan, intent.key)).id); setError(''); }
    catch (error) {
      setError('Recovery unavailable. Keep this confirmation reference; no new installation was requested.');
      if (error instanceof ApiFailure && [404, 409, 422].includes(error.status ?? 0)) {
        try { acceptJob((await provisioning.recover(intent.key)).id); }
        catch (lookup) {
          if (lookup instanceof ApiFailure && lookup.status === 404) {
            setRejected(true);
            setError('Confirmation rejected and no committed job was found. Clear the rejected confirmation to run a new preflight.');
          }
        }
      }
    }
    finally { setBusy(false); }
  }
  function clearReference(unavailable = false) {
    try { sessionStorage.removeItem('nimbusops.setup.job.v1'); sessionStorage.removeItem(intentStorage); }
    catch { setError('Unable to clear local storage.'); return; }
    setJobId(''); setJob(null); setIntent(null); setMissing(false); setRejected(false); setPlan(null); setConfirmed(false); setSelected('');
    setError(unavailable ? 'Only the local reference was cleared; the job was not cancelled. Reconcile the prior installation before trying that target again.' : '');
  }
  async function retry() {
    setBusy(true); setError('');
    try {
      const result = await provisioning.retry(jobId);
      try { sessionStorage.removeItem('nimbusops.setup.job.v1'); } catch { /* No secret is stored. */ }
      setSelected(result.target_id); setJobId(''); setJob(null); setPlan(null); setConfirmed(false);
    } catch { setError('Retry blocked: operator reconciliation is required.'); }
    finally { setBusy(false); }
  }
  return <section className="space-y-4" aria-label="Automatic Setup">
    <h2 className="text-xl font-semibold">Automatic Setup — recommended</h2>
    <p>Only operator-authorized Ubuntu 24.04 amd64 targets are available. SSH credentials and host keys are configured securely on the server, never entered in this browser.</p>
    {loaded && targets.length === 0 && <p>No authorized targets. Ask the operator to configure SSH authorization, or use Manual Bootstrap.</p>}
    {error && <p role="alert">{error}</p>}
    {intent && !jobId && <div><p>Confirmation reference: {intent.key}. Installation may already be running.</p>
      <Button disabled={busy} onClick={recover}>Recover same confirmation</Button>
      {rejected && <Button disabled={busy} onClick={() => clearReference()}>Clear rejected confirmation</Button>}</div>}
    {!jobId && !intent && <>
      <label>Authorized target<select value={selected} disabled={busy} onChange={e => {setSelected(e.target.value); setPlan(null); setConfirmed(false);}}>
        <option value="">Select target</option>{targets.map(t => <option key={t.id} value={t.id}>{t.hostname} — {t.address}</option>)}
      </select></label>
      <Button disabled={!selected || busy} onClick={inspect}>Read-only preflight</Button>
      {plan && <div className="space-y-3">
        <h3>Review target and proposed changes</h3>
        <dl>{Object.entries(plan.facts).map(([k,v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
        <ul>{plan.changes.map(change => <li key={change}>{change}</li>)}</ul>
        <p>Approval expires at {new Date(plan.expires_at).toLocaleTimeString()}. Existing identities will never be overwritten.</p>
        <label><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />I authorize these changes on this target.</label>
        <Button disabled={!confirmed || busy || Date.now() >= plan.expires_at} onClick={install}>Confirm installation</Button>
      </div>}
    </>}
    {jobId && <div aria-live="polite"><p>Job: {jobId}</p><p>Status: {job?.state ?? 'PENDING'}</p>
      <ul>{job?.events.map(e => <li key={e.sequence}>{e.code}</li>)}</ul>
      {job?.state === 'SUCCEEDED' ? <p>Enrollment, fresh heartbeat and telemetry verified.</p> : <p>Service startup alone is not proof of success.</p>}
      {job?.reconciliation_required && <p>Do not reinstall or reenroll. An uncertain outcome requires operator reconciliation; blind retry is blocked.</p>}
      {job?.retry_allowed && <Button disabled={busy} onClick={retry}>Retry with new preflight and approval</Button>}
      {job && ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(job.state) && !job.reconciliation_required && <Button onClick={() => clearReference()}>Add another server</Button>}
      {missing && <Button onClick={() => clearReference(true)}>Clear unavailable job reference</Button>}
    </div>}
  </section>;
}
