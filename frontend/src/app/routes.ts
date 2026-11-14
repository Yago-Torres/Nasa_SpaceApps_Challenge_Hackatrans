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

export function hrefFor(id: RouteId, param?: string) {
  return param ? `#/${id}/${encodeURIComponent(param)}` : `#/${id}`;
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
