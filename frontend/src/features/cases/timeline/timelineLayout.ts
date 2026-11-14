/**
 * Pixel layout helpers for the ABB-22 forensic timeline chart (CaseTimeline / TimelineChart).
 * Like `features/chartScale.ts`, these only map values the backend already returned (dates,
 * a backend-assigned severity category) to drawing space. They compute no new statistics,
 * anomalies or significance (frontend/AGENTS.md: scaling for pixels is fine, deriving new
 * scientific values is not).
 */

const DAY_MS = 86_400_000;

/** Calendar day number (UTC) of an ISO date string ("YYYY-MM-DD"), for linear positioning only. */
export function dayNumber(iso: string): number {
  return Date.parse(`${iso}T00:00:00Z`) / DAY_MS;
}

export type DayScale = (iso: string) => number;

/** Linear day-based scale from [minIso, maxIso] to [x0, x1], clamped to the axis. */
export function dayScale(minIso: string, maxIso: string, x0: number, x1: number): DayScale {
  const min = dayNumber(minIso);
  const max = Math.max(dayNumber(maxIso), min + 1); // at least one day wide; guards a zero-width span
  return (iso: string) => {
    const t = Math.min(1, Math.max(0, (dayNumber(iso) - min) / (max - min)));
    return x0 + t * (x1 - x0);
  };
}

/** The first day of each UTC month covering [minIso, maxIso], thinned so labels stay legible. */
export function monthTicks(minIso: string, maxIso: string, maxTicks = 12): { iso: string; date: Date }[] {
  const min = new Date(`${minIso}T00:00:00Z`);
  const max = new Date(`${maxIso}T00:00:00Z`);
  const months: Date[] = [];
  const cur = new Date(Date.UTC(min.getUTCFullYear(), min.getUTCMonth(), 1));
  while (cur <= max) {
    months.push(new Date(cur));
    cur.setUTCMonth(cur.getUTCMonth() + 1);
  }
  const step = Math.max(1, Math.ceil(months.length / maxTicks));
  return months.filter((_, i) => i % step === 0).map((date) => ({ iso: date.toISOString().slice(0, 10), date }));
}

/** The date span the chart should cover: every dated event's start/end plus the incident window. */
export function timelineSpan(
  events: { start: string | null; end: string | null }[],
  incidentStart: string,
  incidentEnd: string | null,
): [string, string] {
  const dates = events.flatMap((e) => [e.start, e.end]).filter((d): d is string => d !== null);
  dates.push(incidentStart, incidentEnd ?? incidentStart);
  return [dates.reduce((a, b) => (a < b ? a : b)), dates.reduce((a, b) => (a > b ? a : b))];
}

/**
 * Greedy interval packing: assigns each dated event in a lane to the first sub-row whose
 * previous occupant ends before this event starts, so overlapping spans (e.g. several
 * hypotheses over the same incident period) draw as stacked rows rather than on top of each
 * other. Order-preserving input is expected to already be sorted by start date.
 */
export function packRows(events: { start: string; end: string }[]): number[] {
  const rowEnds: number[] = [];
  return events.map((e) => {
    const start = dayNumber(e.start);
    const end = Math.max(dayNumber(e.end), start);
    const row = rowEnds.findIndex((occupiedUntil) => occupiedUntil < start);
    if (row === -1) {
      rowEnds.push(end);
      return rowEnds.length - 1;
    }
    rowEnds[row] = end;
    return row;
  });
}

/** Backend-assigned severity category -> relative mark size (no new significance invented). */
export function severitySize(severity: string | undefined): number {
  switch (severity) {
    case 'LARGE_DEPARTURE':
      return 1;
    case 'MODERATE_DEPARTURE':
      return 0.72;
    case 'WITHIN_REFERENCE_SPREAD':
      return 0.48;
    default:
      return 0.6; // NOT_CLASSIFIED or absent
  }
}
