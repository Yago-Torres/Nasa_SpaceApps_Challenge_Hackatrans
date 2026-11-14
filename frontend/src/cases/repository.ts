import type { IncidentCase } from './model';

/**
 * Case storage boundary for ABB-21. The UI talks only to this interface, so swapping the
 * development adapter for the real API (ABB-05/ABB-06, contract request A4) touches one file.
 */
export interface CaseRepository {
  /** True for adapters that must never be presented as production storage. */
  readonly developmentOnly: boolean;
  list(): Promise<IncidentCase[]>;
  get(id: string): Promise<IncidentCase | null>;
  save(c: IncidentCase): Promise<IncidentCase>;
  remove(id: string): Promise<void>;
  clear(): Promise<void>;
}

export class StorageUnavailableError extends Error {
  constructor() {
    super('storage-unavailable');
  }
}

const KEY = 'abb-dev-cases-v1';

/**
 * DEVELOPMENT-ONLY adapter: keeps cases in this browser's localStorage. No account, no
 * server, no sharing. Every screen using it shows a visible development notice, and the
 * user can delete all local data. Replace with an HTTP adapter once /api/v1/cases exists.
 */
export class LocalDevCaseRepository implements CaseRepository {
  readonly developmentOnly = true;

  private read(): IncidentCase[] {
    try {
      const raw = localStorage.getItem(KEY);
      const parsed: unknown = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? (parsed as IncidentCase[]) : [];
    } catch {
      throw new StorageUnavailableError();
    }
  }

  private write(cases: IncidentCase[]) {
    try {
      localStorage.setItem(KEY, JSON.stringify(cases));
    } catch {
      throw new StorageUnavailableError();
    }
  }

  async list() {
    return this.read().sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  }

  async get(id: string) {
    return this.read().find((c) => c.id === id) ?? null;
  }

  async save(c: IncidentCase) {
    const all = this.read();
    const saved = { ...c, updatedAt: new Date().toISOString(), version: c.version + 1 };
    const i = all.findIndex((x) => x.id === c.id);
    if (i >= 0) all[i] = saved;
    else all.push(saved);
    this.write(all);
    return saved;
  }

  async remove(id: string) {
    this.write(this.read().filter((c) => c.id !== id));
  }

  async clear() {
    try {
      localStorage.removeItem(KEY);
    } catch {
      throw new StorageUnavailableError();
    }
  }
}

let instance: CaseRepository | null = null;
export function caseRepository(): CaseRepository {
  instance ??= new LocalDevCaseRepository();
  return instance;
}
/** Test hook. */
export function setCaseRepository(repo: CaseRepository | null) {
  instance = repo;
}
