import { useSyncExternalStore } from 'react';
import type { SessionOut, UserOut } from './types';

/**
 * Signed-in session (ABB-05, ADR-0004). The opaque bearer token lives in memory and in this
 * tab's sessionStorage only, so a reload keeps the user signed in and closing the tab signs
 * them out. It is never written to localStorage, put in a URL or logged.
 */
export type Session = { token: string; expiresAt: string; user: UserOut };

const KEY = 'abb-session-v1';
let current: Session | null | undefined; // undefined = not read from storage yet
const listeners = new Set<() => void>();

function isSession(value: unknown): value is Session {
  const s = value as Session | null;
  return !!s && typeof s.token === 'string' && s.token !== '' && typeof s.expiresAt === 'string' && typeof s.user?.display_name === 'string';
}

function expired(s: Session) {
  const at = Date.parse(s.expiresAt);
  return !Number.isFinite(at) || at <= Date.now();
}

function forget() {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* storage blocked: memory copy is enough */
  }
}

function notify() {
  listeners.forEach((fn) => fn());
}

/** Current session, or null when signed out or expired. Safe to call during render. */
export function getSession(): Session | null {
  if (current === undefined) {
    try {
      const parsed: unknown = JSON.parse(sessionStorage.getItem(KEY) ?? 'null');
      current = isSession(parsed) ? parsed : null;
    } catch {
      current = null;
    }
  }
  if (current && expired(current)) {
    current = null;
    forget();
  }
  return current;
}

export function setSession(out: SessionOut) {
  current = { token: out.access_token, expiresAt: out.expires_at, user: out.user };
  try {
    sessionStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    /* storage blocked: the session lasts until reload */
  }
  notify();
}

export function clearSession() {
  const had = current;
  current = null;
  forget();
  if (had) notify();
}

export function subscribeSession(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function useSession(): Session | null {
  return useSyncExternalStore(subscribeSession, getSession, getSession);
}

/** Test hook: forget the in-memory copy so the next read comes from sessionStorage. */
export function resetSessionCache() {
  current = undefined;
}
