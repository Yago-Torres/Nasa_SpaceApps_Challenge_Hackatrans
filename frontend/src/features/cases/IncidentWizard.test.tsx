import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { I18nProvider } from '../../i18n/I18n';
import { App } from '../../app/App';
import { setCaseRepository } from '../../cases/repository';

function go(hash: string) {
  act(() => {
    window.location.hash = hash;
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
}

beforeEach(() => {
  localStorage.clear();
  setCaseRepository(null);
});
afterEach(() => {
  cleanup();
  window.location.hash = '';
});

describe('ABB-21 incident wizard', () => {
  it('creates a case from scratch, lists it with a rounded location, and edits it again', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/cases/new';
    render(<I18nProvider lang="en"><App /></I18nProvider>);

    // Step 1: where (default privacy tier is "Approximate area", 0.1°)
    await user.type(screen.getByLabelText('Case name'), 'Wheat loss, north plot');
    await user.type(screen.getByLabelText('Latitude'), '41.6537');
    await user.type(screen.getByLabelText('Longitude'), '-0.8773');
    expect(screen.getByText(/Reviewers see: 41[.,]650, −0[.,]850/)).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    // Step 2: crops
    await user.type(screen.getByLabelText('Year'), '2022');
    await user.type(screen.getByLabelText('Crop'), 'durum wheat');
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    // Step 3: incident
    await user.type(screen.getByLabelText('Year of the incident'), '2022');
    await user.type(screen.getByLabelText('What you saw'), 'Yellowing from the edges in May.');
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    // Step 4: constraints (optional), then review lists the gaps as missing data
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getByText('Whether the field is irrigated')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Save case' }));
    expect(await screen.findByRole('button', { name: 'Investigate with NASA data' })).toBeTruthy();

    // List: the case appears, shared only as the rounded cell centre
    go('#/cases');
    const table = await screen.findByRole('table');
    const row = within(table).getByRole('row', { name: /Wheat loss, north plot/ });
    expect(row.textContent).toMatch(/41[.,]65, −0[.,]85 \(±0[.,]05°\)/);
    expect(row.textContent).not.toContain('41.6537');

    // Edit again
    await user.click(within(row).getByRole('link', { name: 'Edit' }));
    const title = await screen.findByLabelText('Case name');
    expect((title as HTMLInputElement).value).toBe('Wheat loss, north plot');
    await user.clear(title);
    await user.type(title, 'Wheat loss, lower plot');
    for (let i = 0; i < 4; i++) await user.click(screen.getByRole('button', { name: 'Continue' }));
    await user.click(screen.getByRole('button', { name: 'Save case' }));
    await screen.findByRole('button', { name: 'Investigate with NASA data' });
    go('#/cases');
    expect(await screen.findByRole('row', { name: /Wheat loss, lower plot/ })).toBeTruthy();
  });

  it('keeps what was typed when a field is invalid and focuses the first error', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/cases/new';
    render(<I18nProvider lang="en"><App /></I18nProvider>);
    await user.type(screen.getByLabelText('Case name'), 'Barley patch');
    await user.type(screen.getByLabelText('Latitude'), '95');
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getByText('Use a number from −90 to 90.')).toBeTruthy();
    expect(screen.getByText('Use a number from −180 to 180.')).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText('Latitude')));
    expect((screen.getByLabelText('Case name') as HTMLInputElement).value).toBe('Barley patch');
    expect((screen.getByLabelText('Latitude') as HTMLInputElement).value).toBe('95');
  });

  it('labels development storage so it is never mistaken for production', () => {
    window.location.hash = '#/cases';
    render(<I18nProvider lang="es"><App /></I18nProvider>);
    expect(screen.getByText('Almacenamiento de desarrollo')).toBeTruthy();
  });
});
