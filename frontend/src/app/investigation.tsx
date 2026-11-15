import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import type { ClimateResponse, Paper, Rotation } from '../api/types';

/**
 * The one-off investigation of this browser tab. In memory only: nothing is persisted
 * until accounts and case storage exist (ABB-05, ABB-06). Results are kept exactly as
 * the API returned them; nothing here is computed or invented.
 */
export type InvestigationInput = { latitude: string; longitude: string; year: string };

type Store = {
  input: InvestigationInput;
  setInput: (input: InvestigationInput) => void;
  climate: ClimateResponse | null;
  setClimate: (c: ClimateResponse | null) => void;
  papers: Paper[];
  setPapers: (p: Paper[]) => void;
  query: string;
  setQuery: (q: string) => void;
  rotations: Rotation[];
  setRotations: (r: Rotation[]) => void;
};

const Ctx = createContext<Store | null>(null);

/** Same rule as the backend default (climate.py): the 10 years before the event year, from POWER's 1981. */
export const REFERENCE_YEARS = 10;
export const FIRST_EVENT_YEAR = 1984; // 1981–1983 is the shortest reference window the backend accepts
export function referenceWindow(year: number): { start: number; end: number } {
  return { start: Math.max(1981, year - REFERENCE_YEARS), end: year - 1 };
}

export function InvestigationProvider({ children }: { children: ReactNode }) {
  const [input, setInput] = useState<InvestigationInput>({ latitude: '', longitude: '', year: '' });
  const [climate, setClimate] = useState<ClimateResponse | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [query, setQuery] = useState('');
  const [rotations, setRotations] = useState<Rotation[]>([]);
  const value = useMemo(
    () => ({ input, setInput, climate, setClimate, papers, setPapers, query, setQuery, rotations, setRotations }),
    [input, climate, papers, query, rotations],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useInvestigation() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useInvestigation must be used inside <InvestigationProvider>');
  return ctx;
}

export type FieldErrors = Partial<Record<keyof InvestigationInput, true>>;

/** Mirrors the backend's own validation (app.py) so users get the message before a request. */
export function validateInput(input: InvestigationInput, currentYear = new Date().getFullYear()): { errors: FieldErrors; value?: { latitude: number; longitude: number; year: number } } {
  const parse = (s: string) => (s.trim() === '' ? NaN : Number(s.trim().replace('−', '-').replace(',', '.')));
  const latitude = parse(input.latitude);
  const longitude = parse(input.longitude);
  const year = parse(input.year);
  const errors: FieldErrors = {};
  if (!(latitude >= -90 && latitude <= 90)) errors.latitude = true;
  if (!(longitude >= -180 && longitude <= 180)) errors.longitude = true;
  if (!(Number.isInteger(year) && year >= FIRST_EVENT_YEAR && year <= currentYear)) errors.year = true;
  return Object.keys(errors).length ? { errors } : { errors, value: { latitude, longitude, year } };
}
