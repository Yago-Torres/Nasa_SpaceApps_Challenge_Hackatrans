import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { I18nProvider } from '../../i18n/I18n';
import { getSession, resetSessionCache, setSession } from '../../api/session';
import { AccountDataPanel } from './AccountDataPanel';

const USER = { id: 'u1', email: 'owner@example.org', display_name: 'Owner', created_at: '2026-01-01T00:00:00Z' };
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
beforeEach(() => { resetSessionCache(); setSession({ access_token: 'token', token_type: 'bearer', expires_at: '2099-01-01T00:00:00Z', user: USER }); });
afterEach(() => { cleanup(); sessionStorage.clear(); resetSessionCache(); vi.restoreAllMocks(); });

describe('Account data UI (ABB-28 / ABB-33)', () => {
  it('requires explicit confirmation and keeps the valid session after a wrong confirmation password', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(401, { detail: 'Incorrect password.' }));
    const user = userEvent.setup(); render(<I18nProvider lang="en"><AccountDataPanel /></I18nProvider>);
    await user.click(screen.getByRole('button', { name: 'Close account' }));
    const submit = screen.getByRole('button', { name: 'Permanently close account' });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    await user.type(screen.getByLabelText('Password'), 'wrong-password');
    await user.click(screen.getByLabelText('I understand that my owned cases will be permanently erased.'));
    await user.click(submit);
    expect(await screen.findByText('The confirmation password is incorrect. Your account was not changed.')).toBeTruthy();
    expect(getSession()?.token).toBe('token');
  });
});
