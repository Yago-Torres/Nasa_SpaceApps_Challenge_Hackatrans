/**
 * Shared UI components of the Field Survey design system
 * (.claude/skills/agro-design-system/references/components.md). Changing one is a
 * cross-team change under ABB-20.
 */
import { forwardRef, useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from 'react';
import { AlertTriangle, Check, Clock, Construction, Info, LoaderCircle } from 'lucide-react';
import { useI18n } from '../i18n/I18n';

/* ── Evidence legend ─────────────────────────────────────────────── */

export type EvidenceKind =
  | 'OBSERVED'
  | 'FARMER_REPORTED'
  | 'LITERATURE_REVIEWED'
  | 'HYPOTHESIS'
  | 'MODEL_SCENARIO'
  | 'ILLUSTRATIVE'
  | 'MISSING_DATA';

const SYMBOL: Record<EvidenceKind, string> = {
  OBSERVED: 'observed',
  FARMER_REPORTED: 'farmer',
  LITERATURE_REVIEWED: 'literature',
  HYPOTHESIS: 'hypothesis',
  MODEL_SCENARIO: 'model',
  ILLUSTRATIVE: 'illustrative',
  MISSING_DATA: 'missing',
};

/** Inline sprite with one cartographic symbol per evidence kind. Render once in the shell. */
export function LegendSprite() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true" focusable="false">
      <symbol id="s-observed" viewBox="0 0 12 12"><rect x="1" y="1" width="10" height="10" fill="currentColor" /></symbol>
      <symbol id="s-farmer" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5" fill="currentColor" /></symbol>
      <symbol id="s-literature" viewBox="0 0 12 12"><path d="M6 1 11.2 10.5H.8z" fill="currentColor" /></symbol>
      <symbol id="s-hypothesis" viewBox="0 0 12 12"><circle cx="6" cy="6" r="4.6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeDasharray="2.2 1.6" /></symbol>
      <symbol id="s-model" viewBox="0 0 12 12"><rect x="1.2" y="1.2" width="9.6" height="9.6" fill="none" stroke="currentColor" strokeWidth="1.4" /><path d="M1.5 7.5 7.5 1.5M1.5 11 11 1.5M5 11 11 5" stroke="currentColor" strokeWidth="1.2" /></symbol>
      <symbol id="s-illustrative" viewBox="0 0 12 12"><path d="M6 .8 11.2 6 6 11.2.8 6z" fill="none" stroke="currentColor" strokeWidth="1.6" /></symbol>
      <symbol id="s-missing" viewBox="0 0 12 12"><rect x="1.2" y="1.2" width="9.6" height="9.6" fill="none" stroke="currentColor" strokeWidth="1.4" strokeDasharray="1.4 1.6" /></symbol>
    </svg>
  );
}

export function EvidenceSymbol({ kind }: { kind: EvidenceKind }) {
  return (
    <svg className={`sym ev--${SYMBOL[kind]}`} aria-hidden="true">
      <use href={`#s-${SYMBOL[kind]}`} />
    </svg>
  );
}

/** Symbol + label (+ optional detail). `symbolOnly` keeps the label for screen readers. */
export function EvidenceLabel({ kind, detail, symbolOnly }: { kind: EvidenceKind; detail?: string; symbolOnly?: boolean }) {
  const { t } = useI18n();
  const label = t(`evidence.${kind}`) + (detail ? ` · ${detail}` : '');
  return (
    <span className={`ev ev--${SYMBOL[kind]}`} data-kind={kind}>
      <EvidenceSymbol kind={kind} />
      {symbolOnly ? <span className="sr-only">{label}</span> : label}
    </span>
  );
}

/* ── Button ──────────────────────────────────────────────────────── */

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'text';
  busy?: boolean;
  icon?: ReactNode;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', busy, icon, children, className, disabled, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={`btn btn--${variant}${className ? ` ${className}` : ''}`}
      aria-busy={busy || undefined}
      disabled={busy || disabled}
      {...rest}
    >
      {busy ? <LoaderCircle className="spin" aria-hidden="true" /> : icon}
      <span>{children}</span>
    </button>
  );
});

/** Link styled as a button (navigation, not an action). */
export function ButtonLink({ variant = 'secondary', href, icon, children }: { variant?: 'primary' | 'secondary'; href: string; icon?: ReactNode; children: ReactNode }) {
  return (
    <a className={`btn btn--${variant}`} href={href}>
      <span>{children}</span>
      {icon}
    </a>
  );
}

/* ── Field ───────────────────────────────────────────────────────── */

type FieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> & {
  label: string;
  hint?: string;
  error?: string;
  unit?: string;
};

export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field({ label, hint, error, unit, ...input }, ref) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errId = `${id}-err`;
  const describedBy = [error ? errId : null, hint ? hintId : null].filter(Boolean).join(' ') || undefined;
  return (
    <div className={`field${error ? ' bad' : ''}`}>
      <label htmlFor={id}>{label}</label>
      <div className="ctl">
        <input ref={ref} id={id} aria-invalid={error ? true : undefined} aria-describedby={describedBy} autoComplete="off" {...input} />
        {unit && <span className="unit" aria-hidden="true">{unit}</span>}
      </div>
      {error && (
        <span className="err" id={errId}>
          <AlertTriangle aria-hidden="true" />
          {error}
        </span>
      )}
      {hint && !error && <span className="hint" id={hintId}>{hint}</span>}
    </div>
  );
});

/* ── Status message: loading, empty, error, partial, stale, pending, ok ── */

export type StatusTone = 'loading' | 'empty' | 'error' | 'partial' | 'stale' | 'pending' | 'ok';

const TONE_ICON: Record<StatusTone, ReactNode> = {
  loading: <LoaderCircle className="spin" aria-hidden="true" />,
  empty: <Info aria-hidden="true" />,
  error: <AlertTriangle aria-hidden="true" />,
  partial: <AlertTriangle aria-hidden="true" />,
  stale: <Clock aria-hidden="true" />,
  pending: <Construction aria-hidden="true" />,
  ok: <Check aria-hidden="true" />,
};

export function StatusMessage({ tone, title, children, action }: { tone: StatusTone; title: string; children?: ReactNode; action?: ReactNode }) {
  const role = tone === 'error' ? 'alert' : tone === 'loading' || tone === 'partial' || tone === 'ok' ? 'status' : undefined;
  return (
    <div className={`msg msg--${tone}`} role={role}>
      {TONE_ICON[tone]}
      <b>{title}</b>
      {children && <div className="msg-body">{children}</div>}
      {action && <div className="msg-action">{action}</div>}
    </div>
  );
}

/* ── Page header ─────────────────────────────────────────────────── */

export function PageHeader({ title, lead, aside }: { title: string; lead?: string; aside?: ReactNode }) {
  return (
    <header className="page-head">
      <div>
        {/* tabIndex -1 lets the shell move focus here after navigation */}
        <h1 tabIndex={-1} data-page-title>
          {title}
        </h1>
        {lead && <p>{lead}</p>}
      </div>
      {aside}
    </header>
  );
}

/* ── Source label (herbarium-style provenance) ───────────────────── */

export type SourceRow = { label: string; value: ReactNode; mono?: boolean };

export function SourceLabel({ name, kind, rows, limitations }: { name: string; kind: EvidenceKind; rows: SourceRow[]; limitations?: string }) {
  return (
    <article className="label">
      <header>
        <b>{name}</b>
        <EvidenceLabel kind={kind} />
      </header>
      <dl>
        {rows.map((r) => (
          <div key={r.label} className="label-row">
            <dt>{r.label}</dt>
            <dd className={r.mono ? 'mono' : undefined}>{r.value}</dd>
          </div>
        ))}
        {limitations && <dd className="lim">{limitations}</dd>}
      </dl>
    </article>
  );
}
