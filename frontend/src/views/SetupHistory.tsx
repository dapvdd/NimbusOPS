import { useEffect, useRef, useState } from 'react';
import { provisioning, type SetupJobSummary } from '../api/provisioning';
import { Button } from '../ui/Button';

/** Server-backed discovery; never submits, retries or rearms a job. */
export default function SetupHistory({onSelect}: {onSelect: (id: string) => void}) {
  const [jobs, setJobs] = useState<SetupJobSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const generation = useRef(0);
  async function load(offset = 0) {
    const version = ++generation.current;
    setLoading(true); setError('');
    try {
      const result = await provisioning.jobs(offset);
      if (version !== generation.current) return;
      setJobs(previous => offset ? [...previous, ...result.jobs] : result.jobs);
      setTotal(result.total);
    } catch {
      if (version === generation.current) setError('Job history unavailable. Previously shown rows may be stale; refresh to recover.');
    } finally {
      if (version === generation.current) setLoading(false);
    }
  }
  useEffect(() => { void load(); return () => { generation.current++; }; }, []);
  return <section aria-label="Setup job history" className="space-y-3">
    <h3 className="text-lg font-semibold">Previous setup jobs</h3>
    <p>Read-only history for your operator account. Automatic Setup is NOT ACCEPTED for real provisioning until a separate acceptance succeeds.</p>
    <Button disabled={loading} onClick={() => void load()}>Refresh job history</Button>
    {loading && <p role="status">Loading job history…</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && !error && jobs.length === 0 && <p>No previous setup jobs.</p>}
    <ul className="space-y-3">{jobs.map(job => <li key={job.id} className="rounded-lg border border-ink-700 p-3 break-words">
      <p>Job ID: {job.id}</p><p>Target: <span>{job.target_id}</span></p>
      <p>Method: {job.method} — {job.operation}</p>
      <p>Created: {new Date(job.created_at).toISOString()} · Updated: {new Date(job.updated_at).toISOString()}</p>
      <p>State: {job.state === 'SUCCEEDED' ? 'COMPLETED (SUCCEEDED)' : job.state}</p>
      {job.reason_code && <p>Reason: <span>{job.reason_code}</span></p>}
      {job.reconciliation_required && <p>Operator reconciliation required. No reinstall or retry.</p>}
      <Button onClick={() => onSelect(job.id)}>Inspect {job.id}</Button>
    </li>)}</ul>
    {jobs.length < total && !error && <Button disabled={loading} onClick={() => void load(jobs.length)}>Load older setup jobs</Button>}
  </section>;
}
