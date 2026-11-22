import { afterEach, expect, it, vi } from 'vitest';
import { provisioning } from './provisioning';

afterEach(() => vi.unstubAllGlobals());
it('sends preflight as JSON accepted by FastAPI', async () => {
  const fetcher = vi.fn().mockResolvedValue({ok: true, json: async () => ({})});
  vi.stubGlobal('fetch', fetcher);
  await provisioning.preflight('target');
  expect(fetcher.mock.calls[0][1].headers['Content-Type']).toBe('application/json');
});
