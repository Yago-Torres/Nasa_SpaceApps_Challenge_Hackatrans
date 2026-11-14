import { useEffect, useState } from 'react';
import type { MessageKey } from '../i18n/messages';

/** The seven primary screens required by ABB-20. `available` = backed by an endpoint that exists today. */
export const ROUTES = [
  { id: 'dashboard', label: 'nav.dashboard', available: true },
  { id: 'cases', label: 'nav.cases', available: true },
  { id: 'investigation', label: 'nav.investigation', available: true },
  { id: 'evidence', label: 'nav.evidence', available: true },
  { id: 'rotations', label: 'nav.rotations', available: true },
  { id: 'collaboration', label: 'nav.collaboration', available: false },
  { id: 'report', label: 'nav.report', available: true },
] as const satisfies readonly { id: string; label: MessageKey; available: boolean }[];

export type RouteId = (typeof ROUTES)[number]['id'];

/** Hash routing ("#/evidence"): works on any static host and needs no dependency. Unknown → dashboard. */
export function parseHash(hash: string): RouteId {
  const id = hash.replace(/^#\/?/, '').split(/[/?]/)[0];
  return (ROUTES.find((r) => r.id === id)?.id ?? 'dashboard') as RouteId;
}

/** Second hash segment, e.g. "new" or a case id in "#/cases/<id>". */
export function parseParam(hash: string): string | null {
  const parts = hash.replace(/^#\/?/, '').split('?')[0].split('/');
  return parts[1] ? decodeURIComponent(parts[1]) : null;
}

/**
 * Third hash segment of a case route, e.g. "timeline" in "#/cases/<id>/timeline" (ABB-22).
 * Defaults to "details" (the existing IncidentWizard) when absent, so "#/cases/<id>" keeps
 * working unchanged. This is the shared extension point for case sub-screens: ABB-23
 * (Evidence), ABB-25 (Collaboration) and ABB-26 (Report) read this the same way instead of
 * inventing their own routing. The tab id list itself lives in `features/Cases.tsx`
 * (`CASE_TABS`), not here, so routing stays generic.
 */
export function parseCaseTab(hash: string): string {
  const parts = hash.replace(/^#\/?/, '').split('?')[0].split('/');
  return parts[2] ? decodeURIComponent(parts[2]) : 'details';
}

export function hrefFor(id: RouteId, param?: string) {
  return param ? `#/${id}/${encodeURIComponent(param)}` : `#/${id}`;
}

/** Link to a case sub-tab. "details" stays at the canonical "#/cases/<id>" (no third segment). */
export function hrefForCaseTab(caseId: string, tab: string) {
  return tab === 'details' ? hrefFor('cases', caseId) : `#/cases/${encodeURIComponent(caseId)}/${encodeURIComponent(tab)}`;
}

export function useRouteParam(): string | null {
  const [param, setParam] = useState<string | null>(() => parseParam(window.location.hash));
  useEffect(() => {
    const onChange = () => setParam(parseParam(window.location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return param;
}

/** Live case tab id (see `parseCaseTab`). */
export function useCaseTab(): string {
  const [tab, setTab] = useState<string>(() => parseCaseTab(window.location.hash));
  useEffect(() => {
    const onChange = () => setTab(parseCaseTab(window.location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return tab;
}

export function navigate(id: RouteId, param?: string) {
  window.location.hash = hrefFor(id, param);
}

export function useRoute(): RouteId {
  const [route, setRoute] = useState<RouteId>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}
