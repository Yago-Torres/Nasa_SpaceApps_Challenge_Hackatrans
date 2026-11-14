import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { I18nProvider } from '../../i18n/I18n';
import { emptyCase, type IncidentCase } from '../../cases/model';
import { LocationMap, viewerLocationForReadOnlyCase } from './LocationMap';

afterEach(cleanup);

function withServer(overrides: Partial<IncidentCase['server']>, locOverrides: Partial<IncidentCase['location']> = {}): IncidentCase {
  const c = emptyCase(new Date('2026-11-14T10:00:00Z'));
  c.location = { ...c.location, latitude: '41.6537', longitude: '-0.8773', ...locOverrides };
  c.server = {
    status: 'INVESTIGATING', myRole: 'REVIEWER', ownerName: 'Synthetic owner', archived: false,
    fieldId: 'f1', fieldCount: 1, privacyTier: 'APPROXIMATE', locationPrecision: 'APPROXIMATE', ...overrides,
  };
  return c;
}

/**
 * ABB-21 / ADR-0005 hard privacy requirement: LocationMap never draws a precise marker for a
 * viewer who is not authorized to see it. `viewerLocationForReadOnlyCase` is the function that
 * decides this for the read-only case view (reviewers/viewers); these tests exercise exactly the
 * same branches `CaseTitleBlock.sharedAsText` uses, with the server-redacted fields as the only
 * input (never re-deriving privacy from raw coordinates).
 */
describe('viewerLocationForReadOnlyCase (never over-shares to reviewers/viewers)', () => {
  it('a reviewer with APPROXIMATE precision gets the rounded cell centre, not the exact point', () => {
    const c = withServer({ myRole: 'REVIEWER', locationPrecision: 'APPROXIMATE' }, { latitude: '41.65', longitude: '-0.85' });
    expect(viewerLocationForReadOnlyCase(c)).toEqual({ kind: 'rounded', latitude: 41.65, longitude: -0.85, rounding: 0.1 });
  });

  it('a reviewer with REGION_ONLY precision gets only the label, never coordinates', () => {
    const c = withServer({ myRole: 'REVIEWER', locationPrecision: 'REGION_ONLY' }, { regionLabel: 'Ebro valley' });
    expect(viewerLocationForReadOnlyCase(c)).toEqual({ kind: 'region', label: 'Ebro valley' });
  });

  it('a reviewer with NONE precision (or no consent / private tier) sees nothing', () => {
    const c = withServer({ myRole: 'REVIEWER', locationPrecision: 'NONE' });
    expect(viewerLocationForReadOnlyCase(c)).toEqual({ kind: 'hidden' });
  });

  it('a reviewer with EXACT precision (owner consented) sees the precise point', () => {
    const c = withServer({ myRole: 'REVIEWER', locationPrecision: 'EXACT' }, { latitude: '41.6537', longitude: '-0.8773' });
    expect(viewerLocationForReadOnlyCase(c)).toEqual({ kind: 'precise', latitude: 41.6537, longitude: -0.8773 });
  });

  it('a viewer role is treated the same as a reviewer (server precision governs, not the raw tier)', () => {
    const c = withServer({ myRole: 'VIEWER', locationPrecision: 'APPROXIMATE' }, { latitude: '41.65', longitude: '-0.85' });
    expect(viewerLocationForReadOnlyCase(c).kind).toBe('rounded');
  });

  it('an owner/editor always sees the exact stored point regardless of the stored tier', () => {
    const owner = withServer({ myRole: 'OWNER', locationPrecision: 'REGION_ONLY' });
    expect(viewerLocationForReadOnlyCase(owner)).toEqual({ kind: 'precise', latitude: 41.6537, longitude: -0.8773 });
    const editor = withServer({ myRole: 'EDITOR', locationPrecision: 'NONE' });
    expect(viewerLocationForReadOnlyCase(editor)).toEqual({ kind: 'precise', latitude: 41.6537, longitude: -0.8773 });
  });

  it('a new, unsaved case (no server metadata yet) is treated as the owner editing', () => {
    const c = emptyCase();
    c.location = { ...c.location, latitude: '41.6537', longitude: '-0.8773' };
    expect(viewerLocationForReadOnlyCase(c)).toEqual({ kind: 'precise', latitude: 41.6537, longitude: -0.8773 });
  });
});

describe('LocationMap rendering (text alternative + no precise marker without authorization)', () => {
  it('hidden: shows a caption, no map canvas, and no coordinates anywhere in the DOM', () => {
    const { container } = render(<I18nProvider lang="en"><LocationMap viewer={{ kind: 'hidden' }} /></I18nProvider>);
    expect(screen.getByText(/not shown a location/i)).toBeTruthy();
    expect(container.querySelector('.locmap-canvas')).toBeNull();
    expect(container.textContent).not.toMatch(/41\.6/);
  });

  it('region: shows only the label, no map canvas and no coordinates', () => {
    const { container } = render(
      <I18nProvider lang="en"><LocationMap viewer={{ kind: 'region', label: 'Ebro valley' }} /></I18nProvider>,
    );
    expect(screen.getByText(/Ebro valley/)).toBeTruthy();
    expect(container.querySelector('.locmap-canvas')).toBeNull();
  });

  it('rounded: mounts a map canvas and the caption says "approximate", not the exact point', async () => {
    const { container } = render(
      <I18nProvider lang="en"><LocationMap viewer={{ kind: 'rounded', latitude: 41.65, longitude: -0.85, rounding: 0.1 }} /></I18nProvider>,
    );
    await waitFor(() => expect(container.querySelector('.locmap-canvas')).not.toBeNull());
    expect(screen.getByText(/shared area/i)).toBeTruthy();
    expect(screen.queryByText(/showing the exact point/i)).toBeNull();
  });

  it('precise: mounts a map canvas and the caption says the exact point is shown', async () => {
    const { container } = render(
      <I18nProvider lang="en"><LocationMap viewer={{ kind: 'precise', latitude: 41.6537, longitude: -0.8773 }} /></I18nProvider>,
    );
    await waitFor(() => expect(container.querySelector('.locmap-canvas')).not.toBeNull());
    expect(screen.getByText(/exact point/i)).toBeTruthy();
  });

  it('every state renders a figure with a figcaption, giving a text alternative even if tiles never load', () => {
    const { container } = render(<I18nProvider lang="en"><LocationMap viewer={{ kind: 'hidden' }} /></I18nProvider>);
    const figure = container.querySelector('figure.locmap');
    expect(figure).not.toBeNull();
    expect(figure!.querySelector('figcaption')).not.toBeNull();
  });
});
