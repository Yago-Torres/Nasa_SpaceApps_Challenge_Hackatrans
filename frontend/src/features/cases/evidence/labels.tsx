import { CircleDashed } from 'lucide-react';
import type { GraphNodeKind } from '../../../api/types';
import { EvidenceLabel, type EvidenceKind } from '../../../design/components';
import { useI18n } from '../../../i18n/I18n';
import { en, type MessageKey } from '../../../i18n/messages';

/** Translated backend enum, or the code itself when the UI has no wording for it yet (never guessed). */
export function useEnum() {
  const { t } = useI18n();
  return (group: string, code: string | null | undefined) => {
    if (!code) return '—';
    const key = `evx.${group}.${code}`;
    return key in en ? t(key as MessageKey) : code;
  };
}

const LEGEND_KINDS = new Set<string>(['OBSERVED', 'FARMER_REPORTED', 'LITERATURE_REVIEWED', 'HYPOTHESIS', 'MISSING_DATA']);

/**
 * Evidence kind of a graph node with its legend symbol. Literature that nobody reviewed is never
 * shown with the reviewed-literature triangle: it gets the "Metadata only" status instead, and
 * conclusions get a plain text badge (they are people's statements, not a legend kind).
 */
export function NodeKindLabel({ kind }: { kind: GraphNodeKind }) {
  const { t } = useI18n();
  if (LEGEND_KINDS.has(kind)) return <EvidenceLabel kind={kind as EvidenceKind} />;
  if (kind === 'LITERATURE_METADATA') return <span className="chip-meta">{t('evidence.metadataOnly')}</span>;
  return <span className="chip-meta chip-meta--plain">{t('evx.conclusion')}</span>;
}

/** Unmistakable "not reviewed" status: icon + text, never colour alone. */
export function NotReviewed({ status }: { status: string }) {
  const toEnum = useEnum();
  const { t } = useI18n();
  return (
    <span className="not-reviewed">
      <CircleDashed aria-hidden="true" />
      {t('evx.notReviewed')} · {toEnum('review', status)}
    </span>
  );
}

/** The registered DOI exactly as the backend returned it (an https://doi.org/ URL), or a plain statement that there is none. */
export function DoiLink({ doi, status }: { doi: string | null; status?: string | null }) {
  const { t } = useI18n();
  const toEnum = useEnum();
  if (!doi) return <span className="muted">{t('evx.noDoi')}</span>;
  return (
    <span className="doi">
      <a href={doi} target="_blank" rel="noreferrer noopener">{doi.replace(/^https:\/\/doi\.org\//, 'doi:')}<span className="sr-only"> {t('ev.newTab')}</span></a>
      {status && <span className="muted"> · {toEnum('doi', status)}</span>}
    </span>
  );
}
