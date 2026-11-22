import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, it, expect, vi } from 'vitest';
import AutomaticSetup from '../AutomaticSetup';
vi.mock('../SetupHistory', () => ({default: ({onSelect}: {onSelect: (id: string) => void}) => <button onClick={() => onSelect('old-job')}>Inspect old-job</button>}));
afterEach(() => {vi.restoreAllMocks(); sessionStorage.clear();});

it('opens a discovered job and clears stale previous detail without retry controls', async () => {
  const { provisioning } = await import('../../api/provisioning');
  vi.spyOn(provisioning, 'targets').mockResolvedValue({targets: []});
  vi.spyOn(provisioning, 'job').mockResolvedValue({id: 'old-job', state: 'FAILED', step: 'REVALIDATE', reason_code: 'REJECTED', reconciliation_required: false, retry_allowed: true, events: []});
  render(<AutomaticSetup />);
  fireEvent.click(screen.getByRole('button', {name: 'Inspect old-job'}));
  expect(await screen.findByText('Reason: REJECTED')).toBeInTheDocument();
  expect(screen.queryByRole('button', {name: /retry with/i})).not.toBeInTheDocument();
});

it('does not discard an uncertain confirmation when inspecting history', async () => {
  const { provisioning } = await import('../../api/provisioning');
  const pending = JSON.stringify({key: 'uncertain-key', plan: {target_id: 'target'}});
  sessionStorage.setItem('nimbusops.setup.confirm.v1', pending);
  vi.spyOn(provisioning, 'targets').mockResolvedValue({targets: []});
  vi.spyOn(provisioning, 'recover').mockRejectedValue(new Error('offline'));
  vi.spyOn(provisioning, 'job').mockResolvedValue({id: 'old-job', state: 'VERIFYING', step: 'INSTALL_ADMITTED', reason_code: null, reconciliation_required: true, retry_allowed: false, events: []});
  render(<AutomaticSetup />);
  fireEvent.click(screen.getByRole('button', {name: 'Inspect old-job'}));
  await screen.findByText('Step: INSTALL_ADMITTED');
  expect(sessionStorage.getItem('nimbusops.setup.confirm.v1')).toBe(pending);
});

it('does not offer reference-clearing actions for an inspected terminal job while a confirmation is unresolved', async () => {
  const { provisioning } = await import('../../api/provisioning');
  const pending = JSON.stringify({key: 'uncertain-key', plan: {target_id: 'target'}});
  sessionStorage.setItem('nimbusops.setup.confirm.v1', pending);
  vi.spyOn(provisioning, 'targets').mockResolvedValue({targets: []});
  vi.spyOn(provisioning, 'recover').mockRejectedValue(new Error('offline'));
  vi.spyOn(provisioning, 'job').mockResolvedValue({id: 'old-job', state: 'FAILED', step: 'REVALIDATE', reason_code: 'REJECTED', reconciliation_required: false, retry_allowed: true, events: []});
  render(<AutomaticSetup />);
  fireEvent.click(screen.getByRole('button', {name: 'Inspect old-job'}));
  await screen.findByText('Step: REVALIDATE');
  expect(screen.queryByRole('button', {name: /add another server|clear unavailable job reference/i})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name: 'Return to unresolved confirmation'}));
  expect(await screen.findByRole('button', {name: 'Recover same confirmation'})).toBeInTheDocument();
  expect(sessionStorage.getItem('nimbusops.setup.confirm.v1')).toBe(pending);
});

it('shows preserved uncertain job step and reason without claiming enrollment or offering retry', async () => {
  const { provisioning } = await import('../../api/provisioning');
  sessionStorage.setItem('nimbusops.setup.job.v1', '007ab9c1-9a05-4a43-9097-474b864e4d4b');
  vi.spyOn(provisioning, 'targets').mockResolvedValue({targets: []});
  vi.spyOn(provisioning, 'job').mockResolvedValue({id: '007ab9c1-9a05-4a43-9097-474b864e4d4b', state: 'VERIFYING', step: 'INSTALL_ADMITTED', reason_code: 'RECONCILIATION_REQUIRED', reconciliation_required: true, retry_allowed: false, events: []});
  render(<AutomaticSetup />);
  expect(await screen.findByText(/Step: INSTALL_ADMITTED/)).toBeInTheDocument();
  expect(screen.getByText(/Reason: RECONCILIATION_REQUIRED/)).toBeInTheDocument();
  expect(screen.queryByText(/Enrollment, fresh heartbeat/)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', {name: /retry|add another/i})).not.toBeInTheDocument();
});

it('renders only allowlisted numeric transport diagnostics with uncertainty warning', async () => {
  const { provisioning } = await import('../../api/provisioning');
  sessionStorage.setItem('nimbusops.setup.job.v1', 'diagnostic');
  vi.spyOn(provisioning, 'targets').mockResolvedValue({targets: []});
  vi.spyOn(provisioning, 'job').mockResolvedValue({id: 'diagnostic', state: 'VERIFYING', step: 'INSTALL_ADMITTED', reason_code: 'RECONCILIATION_REQUIRED', reconciliation_required: true, retry_allowed: false,
    events: [{sequence: 1, code: 'INSTALL_TRANSPORT_FAILED', at: 0, safe_detail: {transport_exit_status: 73}}]});
  render(<AutomaticSetup />);
  expect(await screen.findByText(/Transport exit status: 73/)).toHaveTextContent(/not proof.*rollback/i);
});

it('allows fresh preflight after definitive rejection of a never-dispatched intent', async () => {
  const { provisioning } = await import('../../api/provisioning');
  const { ApiFailure } = await import('../../api/client');
  sessionStorage.setItem('nimbusops.setup.confirm.v1', JSON.stringify({key: 'expired-key', plan: {
    target_id: 'target', validation_id: 'v', approval_hash: 'hash', expires_at: 0, facts: {}, changes: []}}));
  vi.spyOn(provisioning, 'targets').mockResolvedValue({targets: []});
  vi.spyOn(provisioning, 'recover').mockRejectedValue(new ApiFailure('http', 'not found', 404));
  vi.spyOn(provisioning, 'confirm').mockRejectedValue(new ApiFailure('http', 'invalid approval', 409));
  render(<AutomaticSetup />);
  fireEvent.click(await screen.findByRole('button', {name: 'Recover same confirmation'}));
  fireEvent.click(await screen.findByRole('button', {name: /clear rejected confirmation/i}));
  expect(screen.getByLabelText('Authorized target')).toBeInTheDocument();
  expect(sessionStorage.getItem('nimbusops.setup.confirm.v1')).toBeNull();
});

it('fails closed without authorized targets and never asks for credentials', async () => {
  const { provisioning } = await import('../../api/provisioning');
  vi.spyOn(provisioning, 'targets').mockResolvedValue({targets: []});
  render(<AutomaticSetup />);
  expect(await screen.findByText(/no authorized targets/i)).toBeInTheDocument();
  expect(screen.queryByLabelText(/password|private key/i)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', {name: /confirm installation/i})).not.toBeInTheDocument();
});

it('recovers a persisted confirmation after refresh without dispatching again', async () => {
  const { provisioning } = await import('../../api/provisioning');
  sessionStorage.setItem('nimbusops.setup.confirm.v1', JSON.stringify({key: 'stable-key', plan: {
    target_id: 'target', validation_id: 'v', approval_hash: 'hash', expires_at: 0, facts: {}, changes: []}}));
  vi.spyOn(provisioning, 'targets').mockResolvedValue({targets: []});
  const recover = vi.spyOn(provisioning, 'recover').mockResolvedValue({id: 'recovered', state: 'PENDING'});
  const confirm = vi.spyOn(provisioning, 'confirm');
  vi.spyOn(provisioning, 'job').mockResolvedValue({id: 'recovered', state: 'VERIFYING', step: 'INSTALL_ADMITTED',
    reason_code: null, reconciliation_required: true, retry_allowed: false, events: []});
  render(<AutomaticSetup />);
  expect(await screen.findByText('Job: recovered')).toBeInTheDocument();
  expect(recover).toHaveBeenCalledWith('stable-key');
  expect(confirm).not.toHaveBeenCalled();
  expect(screen.queryByRole('button', {name: /add another/i})).not.toBeInTheDocument();
});

it('lets a terminal job clear only its local reference and select another target', async () => {
  const { provisioning } = await import('../../api/provisioning');
  sessionStorage.setItem('nimbusops.setup.job.v1', 'done');
  vi.spyOn(provisioning, 'targets').mockResolvedValue({targets: [{id: 'next', hostname: 'next-vm', address: '192.0.2.2'}]});
  vi.spyOn(provisioning, 'job').mockResolvedValue({id: 'done', state: 'SUCCEEDED', step: 'DONE',
    reason_code: null, reconciliation_required: false, retry_allowed: false, events: []});
  render(<AutomaticSetup />);
  fireEvent.click(await screen.findByRole('button', {name: /add another server/i}));
  expect(screen.getByLabelText('Authorized target')).toBeInTheDocument();
  expect(sessionStorage.getItem('nimbusops.setup.job.v1')).toBeNull();
});

it('stops polling a missing job and provides an explicit local-reference escape', async () => {
  const { provisioning } = await import('../../api/provisioning');
  const { ApiFailure } = await import('../../api/client');
  sessionStorage.setItem('nimbusops.setup.job.v1', 'missing');
  vi.spyOn(provisioning, 'targets').mockResolvedValue({targets: []});
  vi.spyOn(provisioning, 'job').mockRejectedValue(new ApiFailure('http', 'missing', 404));
  render(<AutomaticSetup />);
  fireEvent.click(await screen.findByRole('button', {name: /clear unavailable job reference/i}));
  expect(screen.getByLabelText('Authorized target')).toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent(/not cancelled|reconcile/i);
});

it('requires target review and explicit approval before dispatch', async () => {
  const { provisioning } = await import('../../api/provisioning');
  vi.spyOn(provisioning, 'targets').mockResolvedValue({targets: [{id: 'target', hostname: 'new-vm', address: '192.0.2.1'}]});
  vi.spyOn(provisioning, 'preflight').mockResolvedValue({target_id: 'target', validation_id: 'v', approval_hash: 'hash',
    expires_at: Date.now()+300000, facts: {hostname: 'new-vm', os: 'Ubuntu 24.04'}, changes: ['No Docker permissions']});
  const confirm = vi.spyOn(provisioning, 'confirm').mockResolvedValue({id: 'j', state: 'PENDING'});
  vi.spyOn(provisioning, 'job').mockResolvedValue({id: 'j', state: 'SUCCEEDED', step: 'DONE',
    reason_code: null, reconciliation_required: false, retry_allowed: false, events: []});
  render(<AutomaticSetup />);
  await screen.findByRole('option', {name: /new-vm/});
  fireEvent.change(screen.getByLabelText('Authorized target'), {target: {value: 'target'}});
  fireEvent.click(screen.getByRole('button', {name: 'Read-only preflight'}));
  const install = await screen.findByRole('button', {name: 'Confirm installation'});
  expect(install).toBeDisabled();
  expect(confirm).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(install);
  await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
  expect(sessionStorage.getItem('nimbusops.setup.job.v1')).toBe('j');
  expect(await screen.findByText(/fresh heartbeat and telemetry verified/i)).toBeInTheDocument();
});

it('persists intent before dispatch and reuses its key after a lost response', async () => {
  const { provisioning } = await import('../../api/provisioning');
  vi.spyOn(provisioning, 'targets').mockResolvedValue({targets: [{id: 'target', hostname: 'new-vm', address: '192.0.2.1'}]});
  vi.spyOn(provisioning, 'preflight').mockResolvedValue({target_id: 'target', validation_id: 'v', approval_hash: 'hash',
    expires_at: Date.now()+300000, facts: {}, changes: []});
  vi.spyOn(provisioning, 'recover').mockRejectedValue(new Error('network'));
  const keys: string[] = [];
  vi.spyOn(provisioning, 'confirm').mockImplementation(async (_plan, key) => {
    expect(JSON.parse(sessionStorage.getItem('nimbusops.setup.confirm.v1')!).key).toBe(key);
    keys.push(key);
    if (keys.length === 1) throw new Error('response lost');
    return {id: 'same-job', state: 'VERIFYING'};
  });
  vi.spyOn(provisioning, 'job').mockResolvedValue({id: 'same-job', state: 'VERIFYING', step: 'INSTALL_ADMITTED',
    reason_code: null, reconciliation_required: true, retry_allowed: false, events: []});
  render(<AutomaticSetup />);
  fireEvent.change(await screen.findByLabelText('Authorized target'), {target: {value: 'target'}});
  fireEvent.click(screen.getByRole('button', {name: 'Read-only preflight'}));
  fireEvent.click(await screen.findByRole('checkbox'));
  fireEvent.click(screen.getByRole('button', {name: 'Confirm installation'}));
  const recover = await screen.findByRole('button', {name: 'Recover same confirmation'});
  await waitFor(() => expect(recover).not.toBeDisabled());
  fireEvent.click(recover);
  expect(await screen.findByText('Job: same-job')).toBeInTheDocument();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  expect(screen.queryByRole('button', {name: /add another/i})).not.toBeInTheDocument();
});

it('does not dispatch when durable confirmation storage is blocked', async () => {
  const { provisioning } = await import('../../api/provisioning');
  vi.spyOn(provisioning, 'targets').mockResolvedValue({targets: [{id: 'target', hostname: 'vm', address: '192.0.2.1'}]});
  vi.spyOn(provisioning, 'preflight').mockResolvedValue({target_id: 'target', validation_id: 'v', approval_hash: 'hash',
    expires_at: Date.now()+300000, facts: {}, changes: []});
  const confirm = vi.spyOn(provisioning, 'confirm');
  render(<AutomaticSetup />);
  fireEvent.change(await screen.findByLabelText('Authorized target'), {target: {value: 'target'}});
  fireEvent.click(screen.getByRole('button', {name: 'Read-only preflight'}));
  fireEvent.click(await screen.findByRole('checkbox'));
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage blocked'); });
  fireEvent.click(screen.getByRole('button', {name: 'Confirm installation'}));
  expect(await screen.findByRole('alert')).toHaveTextContent(/storage blocked/i);
  expect(confirm).not.toHaveBeenCalled();
});
