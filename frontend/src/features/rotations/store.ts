/**
 * In-memory, module-level store for the rotation comparator (ABB-24). The app's router
 * (`app/App.tsx`) swaps screens by component type, which unmounts `<Rotations>` on
 * navigation and would otherwise drop local `useState`. Keeping the editable profile and the
 * last backend result in a plain module variable — read through `useSyncExternalStore` —
 * lets the farmer's current selection survive a visit to another screen in the same tab,
 * without any new backend persistence (out of scope; tracked separately) and without
 * touching browser storage (nothing here is written to localStorage/sessionStorage).
 * Resets on a full page reload, which is the documented limitation of this approach.
 */
import { useSyncExternalStore } from 'react';
import type { HypotheticalScenario, ScenarioAnalysis, SensitivityAnalysis } from '../../api/types';
import { emptyProfileForm, type ProfileFormState } from './model';

export type AsyncStatus = 'idle' | 'loading' | 'error' | 'done';

export type RotationsState = {
  form: ProfileFormState;
  /** What-if climate flags (ABB-18 `HYPOTHETICAL`). Historical episodes are deferred; see the PR notes. */
  climateScenarios: HypotheticalScenario[];
  status: AsyncStatus;
  failure: string;
  result: ScenarioAnalysis | null;
  recomputing: boolean;
  sensitivity: SensitivityAnalysis | null;
  sensitivityStatus: AsyncStatus;
  sensitivityFailure: string;
};

function initialState(): RotationsState {
  return {
    form: emptyProfileForm(),
    climateScenarios: [],
    status: 'idle',
    failure: '',
    result: null,
    recomputing: false,
    sensitivity: null,
    sensitivityStatus: 'idle',
    sensitivityFailure: '',
  };
}

let state: RotationsState = initialState();
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

export function getRotationsState(): RotationsState {
  return state;
}

export function setRotationsState(patch: Partial<RotationsState> | ((prev: RotationsState) => Partial<RotationsState>)): void {
  const next = typeof patch === 'function' ? patch(state) : patch;
  state = { ...state, ...next };
  emit();
}

export function resetRotationsState(): void {
  state = initialState();
  emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Subscribes the calling component to the shared store; re-renders on every `setRotationsState`. */
export function useRotationsState(): RotationsState {
  return useSyncExternalStore(subscribe, getRotationsState, getRotationsState);
}
