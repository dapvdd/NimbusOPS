import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import App from '../../App';

afterEach(() => vi.unstubAllGlobals());

it('redirects anonymous browser to dedicated login without fetching operational data', async () => {
  const fetcher = vi.fn(async (url: string) => new Response(JSON.stringify(url.endsWith('/me') ? {error:{message:'expired'}} : {csrf_token:'csrf'}), {status:url.endsWith('/me')?401:200}));
  vi.stubGlobal('fetch',fetcher);
  render(<MemoryRouter initialEntries={['/servers']}><App /></MemoryRouter>);
  expect(await screen.findByRole('heading',{name:'Sign in to NimbusOps'})).toBeInTheDocument();
  expect(fetcher.mock.calls.some(([url])=>url.endsWith('/hosts'))).toBe(false);
});

it('restores viewer session and removes enrollment actions', async () => {
  localStorage.clear();
  vi.stubGlobal('fetch',vi.fn(async (url: string) => new Response(JSON.stringify(
    url.endsWith('/me') ? {operator_id:'v',username:'reader',role:'VIEWER'} :
    url.endsWith('/csrf') ? {csrf_token:'csrf'} :
    url.endsWith('/hosts') ? {hosts:[],count:0} : {status:'ok',version:'test',server_time:new Date().toISOString()}
  ),{status:200})));
  render(<MemoryRouter initialEntries={['/servers']}><App /></MemoryRouter>);
  await waitFor(()=>expect(screen.getByText('reader · VIEWER')).toBeInTheDocument());
  expect(screen.queryByRole('button',{name:'Add Server'})).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Log out'})).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:/remove/i})).not.toBeInTheDocument();
});
