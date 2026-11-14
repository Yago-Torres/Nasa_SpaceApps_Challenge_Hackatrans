import { ApiError, casesApi } from '../api/client';
import type { CaseView } from '../api/types';
import { caseAttributes, changedKeys, fromCaseView, toCaseCreate, toFieldInput } from './mapping';
import type { IncidentCase } from './model';

/**
 * Case storage boundary for ABB-21. Screens talk only to this interface. Since ABB-06 the
 * implementation is the authenticated case API; saving requires sign-in. There is no
 * browser fallback: a case is either on the server or not saved (never mixed).
 */
export interface CaseRepository {
  list(): Promise<IncidentCase[]>;
  /** null when the case does not exist or the user has no access (the API answers 404 for both). */
  get(id: string): Promise<IncidentCase | null>;
  /** Creates the case when it has no `server` meta yet, otherwise updates what changed. */
  save(c: IncidentCase): Promise<IncidentCase>;
  remove(id: string, version: number): Promise<void>;
  /** Make `latest` the base for the next save (after the user resolved a conflict). */
  adopt(latest: IncidentCase): void;
}

/** 409 because someone else saved first. `latest` is the case as it is now on the server. */
export class CaseConflictError extends Error {
  constructor(readonly latest: IncidentCase) {
    super('case-conflict');
    this.name = 'CaseConflictError';
  }
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * HTTP adapter for /api/v1/cases. It remembers the last server state of each case it loaded
 * or saved, sends only the attributes that changed, and always sends that state's version.
 */
export class HttpCaseRepository implements CaseRepository {
  private base = new Map<string, IncidentCase>();

  private remember(view: CaseView): IncidentCase {
    const c = fromCaseView(view);
    this.base.set(c.id, c);
    return c;
  }

  adopt(latest: IncidentCase) {
    this.base.set(latest.id, latest);
  }

  async list() {
    const out = await casesApi.list();
    return out.items.map(fromCaseView);
  }

  async get(id: string) {
    if (!UUID.test(id)) return null;
    try {
      return this.remember(await casesApi.get(id));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }
  }

  async save(c: IncidentCase) {
    if (!c.server) return this.remember(await casesApi.create(toCaseCreate(c)));
    const base = this.base.get(c.id) ?? null;
    let version = base?.version ?? c.version;
    let saved: IncidentCase | null = null;
    try {
      const attrs = changedKeys(base && caseAttributes(base), caseAttributes(c));
      if (Object.keys(attrs).length) {
        saved = this.remember(await casesApi.update(c.id, { version, ...attrs }));
        version = saved.version;
      }
      const field = changedKeys(base && toFieldInput(base), toFieldInput(c));
      if (Object.keys(field).length) {
        saved = this.remember(await casesApi.updateField(c.id, c.server.fieldId, { version, ...field }));
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Reload. A different version means someone else saved first; otherwise the 409 was
        // about the case itself (archived or not editable) and the server detail says why.
        const latest = await casesApi.get(c.id).then(fromCaseView, () => null);
        if (latest && latest.version !== version) throw new CaseConflictError(latest);
      }
      throw err;
    }
    return saved ?? { ...c, version };
  }

  async remove(id: string, version: number) {
    await casesApi.remove(id, version);
    this.base.delete(id);
  }
}

let instance: CaseRepository | null = null;
export function caseRepository(): CaseRepository {
  instance ??= new HttpCaseRepository();
  return instance;
}
/** Test hook. */
export function setCaseRepository(repo: CaseRepository | null) {
  instance = repo;
}

/**
 * Cases saved by the development-only browser adapter that existed before ABB-06
 * (localStorage key below). They contain exact coordinates and were never on a server, so
 * the Cases screen offers to delete them. They are not imported automatically.
 */
const LEGACY_KEY = 'abb-dev-cases-v1';
export const legacyBrowserCases = {
  count(): number {
    try {
      const parsed: unknown = JSON.parse(localStorage.getItem(LEGACY_KEY) ?? '[]');
      return Array.isArray(parsed) ? parsed.length : 0;
    } catch {
      return 0;
    }
  },
  clear() {
    try {
      localStorage.removeItem(LEGACY_KEY);
    } catch {
      /* storage blocked: nothing to delete */
    }
  },
};
