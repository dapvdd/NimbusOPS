import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import SetupHistory from '../SetupHistory';
import { provisioning } from '../../api/provisioning';

afterEach(() => vi.restoreAllMocks());
const job = {id: 'fixture-job', target_id: 'fixture-target', method: 'Automatic Setup', operation: 'INSTALL', created_at: 1000, updated_at: 2000, state: 'VERIFYING', step: 'INSTALL_ADMITTED', reason_code: 'RECONCILIATION_REQUIRED', reconciliation_required: true};

it('discovers previous jobs without browser storage and opens read-only details', async () => {
  vi.spyOn(provisioning, 'jobs').mockResolvedValue({jobs: [job], total: 1});
  const select = vi.fn();
  render(<SetupHistory onSelect={select} />);
  expect(await screen.findByText('fixture-target')).toBeInTheDocument();
  expect(screen.getByText('RECONCILIATION_REQUIRED')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name: 'Inspect fixture-job'}));
  expect(select).toHaveBeenCalledWith('fixture-job');
  expect(screen.queryByRole('button', {name: /retry|rearm/i})).not.toBeInTheDocument();
});

it('distinguishes loading, unavailable, recovered empty history', async () => {
  vi.spyOn(provisioning, 'jobs').mockRejectedValueOnce(new Error('offline')).mockResolvedValue({jobs: [], total: 0});
  render(<SetupHistory onSelect={() => {}} />);
  expect(screen.getByRole('status')).toHaveTextContent('Loading');
  expect(await screen.findByRole('alert')).toHaveTextContent('unavailable');
  expect(screen.queryByText('No previous setup jobs.')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name: 'Refresh job history'}));
  expect(await screen.findByText('No previous setup jobs.')).toBeInTheDocument();
});

it('pages older jobs and refreshes without duplicating rows', async () => {
  const load = vi.spyOn(provisioning, 'jobs').mockResolvedValueOnce({jobs: [job], total: 2})
    .mockResolvedValueOnce({jobs: [{...job, id: 'older-job', state: 'SUCCEEDED', reason_code: null}], total: 2})
    .mockResolvedValue({jobs: [job], total: 1});
  render(<SetupHistory onSelect={() => {}} />);
  fireEvent.click(await screen.findByRole('button', {name: 'Load older setup jobs'}));
  expect(await screen.findByText('State: COMPLETED (SUCCEEDED)')).toBeInTheDocument();
  expect(load).toHaveBeenLastCalledWith(1);
  fireEvent.click(screen.getByRole('button', {name: 'Refresh job history'}));
  await screen.findByRole('button', {name: 'Inspect fixture-job'});
  expect(screen.queryByRole('button', {name: 'Inspect older-job'})).not.toBeInTheDocument();
});
