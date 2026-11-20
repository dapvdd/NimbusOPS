import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, it, expect, vi } from 'vitest';
import AutomaticSetup from '../AutomaticSetup';
afterEach(() => {vi.restoreAllMocks(); sessionStorage.clear();});

it('fails closed without authorized targets and never asks for credentials', async () => {
  const { provisioning } = await import('../../api/provisioning');
  vi.spyOn(provisioning, 'targets').mockResolvedValue({targets: []});
  render(<AutomaticSetup />);
  expect(await screen.findByText(/no authorized targets/i)).toBeInTheDocument();
  expect(screen.queryByLabelText(/password|private key/i)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', {name: /confirm installation/i})).not.toBeInTheDocument();
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
