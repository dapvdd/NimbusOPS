import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { CopyField } from '../CopyField';
afterEach(() => vi.unstubAllGlobals());
it.each([undefined, {writeText: async () => {throw new Error('denied');}}])('reports clipboard failure instead of invented success', async clipboard => {
  vi.stubGlobal('navigator', {clipboard});
  render(<CopyField value="public-reference" />);
  fireEvent.click(screen.getByRole('button', {name: 'Copy to clipboard'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Copy failed');
  expect(screen.queryByText('Copied to clipboard.')).not.toBeInTheDocument();
});
it('confirms copy only after clipboard write resolves', async () => {
  vi.stubGlobal('navigator', {clipboard: {writeText: async () => {}}});
  render(<CopyField value="public-reference" />);
  fireEvent.click(screen.getByRole('button', {name: 'Copy to clipboard'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Copied to clipboard.');
});
