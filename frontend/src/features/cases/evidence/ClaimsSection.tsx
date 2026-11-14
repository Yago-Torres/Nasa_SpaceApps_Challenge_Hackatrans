import { useEffect, useRef, useState } from 'react';
import { api, ApiError, evidenceApi } from '../../../api/client';
import type { ClaimList, EvidenceBasis, Paper } from '../../../api/types';
import { Button, Field, RadioGroup, StatusMessage, TextArea } from '../../../design/components';
import { useI18n } from '../../../i18n/I18n';
import { caseErrorText } from '../caseErrors';
import { ClaimCard } from './ClaimCard';
import { DoiLink } from './labels';

type Filter = 'ALL' | 'UNREVIEWED' | 'REVIEWED';

/** Literature in this case (ABB-14): reviewed and not-reviewed claims, never mixed up. */
export function ClaimsSection({ caseId, canAdd, focusClaim, onChanged }: {
  caseId: string;
  canAdd: boolean;
  focusClaim: { id: string; seq: number } | null;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [list, setList] = useState<ClaimList | null>(null);
  const [failure, setFailure] = useState('');
  const [reload, setReload] = useState(0);
  const [filter, setFilter] = useState<Filter>('ALL');

  useEffect(() => {
    const controller = new AbortController();
    evidenceApi.claims(caseId, controller.signal).then(
      (l) => { setList(l); setFailure(''); },
      (e) => { if (e?.name !== 'AbortError') setFailure(caseErrorText(e, t)); },
    );
    return () => controller.abort();
  }, [caseId, reload]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!focusClaim || !list) return;
    setFilter('ALL');
    const el = document.getElementById(`claim-${focusClaim.id}`);
    el?.scrollIntoView?.({ block: 'start' });
    el?.focus();
  }, [focusClaim, list]);

  const items = (list?.items ?? []).filter((c) => filter === 'ALL' || (filter === 'REVIEWED') === c.is_reviewed);
  const filters: { id: Filter; label: string }[] = list ? [
    { id: 'ALL', label: t('evx.filter.all', { n: list.items.length }) },
    { id: 'UNREVIEWED', label: t('evx.filter.unreviewed', { n: list.unreviewed_count }) },
    { id: 'REVIEWED', label: t('evx.filter.reviewed', { n: list.reviewed_count }) },
  ] : [];

  return (
    <section className="panel" aria-labelledby="evx-claims-h">
      <div className="section-head">
        <h2 id="evx-claims-h">{t('evx.claims.title')}</h2>
        <p>{t('evx.claims.lead')}</p>
      </div>
      {canAdd && <AddStudy caseId={caseId} onAdded={() => { setReload((n) => n + 1); onChanged(); }} />}
      {failure && <StatusMessage tone="error" title={t('evx.claims.error')} action={<Button onClick={() => setReload((n) => n + 1)}>{t('state.retry')}</Button>}>{failure}</StatusMessage>}
      {!list && !failure && <StatusMessage tone="loading" title={t('state.loading')} />}
      {list && list.items.length === 0 && <StatusMessage tone="empty" title={t('evx.claims.noneTitle')}>{canAdd ? t('evx.claims.noneBodyEditor') : t('evx.claims.noneBody')}</StatusMessage>}
      {list && list.items.length > 0 && (
        <>
          {list.unreviewed_count > 0 && (
            <StatusMessage tone="partial" title={t('evx.claims.unreviewedTitle', { n: list.unreviewed_count })}>{t('evx.claims.unreviewedBody')}</StatusMessage>
          )}
          <div className="actions" role="group" aria-label={t('evx.filter.label')}>
            {filters.map((f) => <Button key={f.id} aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>{f.label}</Button>)}
          </div>
          {items.length === 0 ? <p className="muted">{t('evx.filter.empty')}</p> : (
            <div className="claims">{items.map((c) => <ClaimCard key={c.id} caseId={caseId} claim={c} focused={focusClaim?.id === c.id} />)}</div>
          )}
          <ul className="list-plain">{list.limitations.map((l, i) => <li key={i} className="muted">{l}</li>)}</ul>
        </>
      )}
    </section>
  );
}

/**
 * Search OpenAlex and keep a study for this case (OWNER/EDITOR). The paper is registered by its
 * DOI or OpenAlex id (the server fetches and verifies the metadata; nothing is typed by hand) and
 * the claim starts not reviewed whatever is entered here.
 */
function AddStudy({ caseId, onAdded }: { caseId: string; onAdded: () => void }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Paper[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [chosen, setChosen] = useState<Paper | null>(null);
  const [added, setAdded] = useState('');
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);

  async function search(event: React.FormEvent) {
    event.preventDefault();
    const q = query.trim();
    if (q.length < 3 || q.length > 180) { setSearchError(t('ev.queryError')); return; }
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setSearching(true); setSearchError(''); setChosen(null); setAdded('');
    try { setResults(await api.literature(q, controller.signal)); }
    catch (e) { if (!controller.signal.aborted) setSearchError(e instanceof ApiError && e.status === 502 ? t('ev.errorTitle') : caseErrorText(e, t)); }
    finally { if (!controller.signal.aborted) setSearching(false); }
  }

  if (!open) {
    return (
      <div className="stack-tight">
        {added && <StatusMessage tone="ok" title={added}>{t('evx.add.addedBody')}</StatusMessage>}
        <div className="actions"><Button onClick={() => { setOpen(true); setAdded(''); }}>{t('evx.add.open')}</Button></div>
      </div>
    );
  }
  return (
    <div className="add-study stack">
      <form className="stack" role="search" onSubmit={search}>
        <h3>{t('evx.add.title')}</h3>
        <Field label={t('ev.query')} type="search" maxLength={180} value={query} hint={t('ev.queryHint')}
          error={searchError && !results ? searchError : undefined} onChange={(e) => { setQuery(e.target.value); setSearchError(''); }} />
        <div className="actions">
          <Button type="submit" busy={searching}>{searching ? t('ev.searching') : t('ev.search')}</Button>
          <Button variant="text" onClick={() => { setOpen(false); setResults(null); setChosen(null); }}>{t('collab.cancel')}</Button>
        </div>
      </form>
      {searchError && results && <StatusMessage tone="error" title={t('ev.errorTitle')}>{searchError}</StatusMessage>}
      {results && results.length === 0 && <StatusMessage tone="empty" title={t('ev.noResults')} />}
      {results && results.length > 0 && !chosen && (
        <ul className="papers">
          {results.map((p) => (
            <li key={p.openalex_id ?? p.doi ?? p.title}>
              <b>{p.title}</b>
              <span className="meta">
                <span className="chip-meta">{t('evidence.metadataOnly')}</span>
                <span>{p.year ?? t('ev.yearUnknown')}</span>
                <DoiLink doi={p.doi} status={p.doi_status} />
              </span>
              <div className="actions">
                <Button disabled={!p.doi && !p.openalex_id} onClick={() => setChosen(p)}>{t('evx.add.choose')}</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {chosen && (
        <ClaimForm caseId={caseId} paper={chosen} onCancel={() => setChosen(null)}
          onDone={(title) => { setOpen(false); setResults(null); setChosen(null); setQuery(''); setAdded(t('evx.add.added', { title })); onAdded(); }} />
      )}
    </div>
  );
}

function ClaimForm({ caseId, paper, onCancel, onDone }: { caseId: string; paper: Paper; onCancel: () => void; onDone: (title: string) => void }) {
  const { t } = useI18n();
  const [claimText, setClaimText] = useState('');
  const [context, setContext] = useState('');
  const [basis, setBasis] = useState<Extract<EvidenceBasis, 'METADATA_ONLY' | 'ABSTRACT'>>('METADATA_ONLY');
  const [limits, setLimits] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState('');
  const limitations = limits.split('\n').map((l) => l.trim()).filter(Boolean);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (!claimText.trim()) next.claim = t('evx.add.required');
    if (!context.trim()) next.context = t('evx.add.required');
    if (limitations.length === 0) next.limits = t('evx.add.limitsRequired');
    if (limitations.length > 20) next.limits = t('evx.add.limitsMax');
    setErrors(next);
    if (Object.keys(next).length) return;
    setBusy(true); setFailure('');
    try {
      const registered = await evidenceApi.registerPaper(paper.doi ? { doi: paper.doi } : { openalex_id: paper.openalex_id! });
      await evidenceApi.createClaim(caseId, {
        paper_id: registered.id, claim_text: claimText.trim(), study_context: context.trim(), evidence_basis: basis,
        access_basis: basis === 'ABSTRACT' ? 'PUBLIC_ABSTRACT' : 'NONE', limitations,
      });
      onDone(registered.title);
    } catch (e) {
      setFailure(e instanceof ApiError && e.status === 502 ? t('evx.add.sourcesDown') : caseErrorText(e, t));
    } finally { setBusy(false); }
  }

  return (
    <form className="stack claim-form" onSubmit={submit} aria-labelledby="evx-claim-form-h">
      <h3 id="evx-claim-form-h">{t('evx.add.formTitle')}</h3>
      <p><b>{paper.title}</b> {paper.year ? `(${paper.year})` : ''} · <DoiLink doi={paper.doi} status={paper.doi_status} /></p>
      <StatusMessage tone="partial" title={t('evx.add.pendingTitle')}>{t('evx.add.pendingBody')}</StatusMessage>
      <TextArea label={t('evx.add.claim')} hint={t('evx.add.claimHint')} rows={2} maxLength={2000} value={claimText}
        error={errors.claim} onChange={(e) => setClaimText(e.target.value)} />
      <TextArea label={t('evx.add.context')} hint={t('evx.add.contextHint')} rows={2} maxLength={5000} value={context}
        error={errors.context} onChange={(e) => setContext(e.target.value)} />
      <RadioGroup<'METADATA_ONLY' | 'ABSTRACT'> legend={t('evx.add.basis')} name="evx-basis" value={basis} onChange={setBasis}
        options={[
          { value: 'METADATA_ONLY', label: t('evx.basis.METADATA_ONLY'), hint: t('evx.add.basisMetadata') },
          { value: 'ABSTRACT', label: t('evx.basis.ABSTRACT'), hint: t('evx.add.basisAbstract') },
        ]} />
      <TextArea label={t('evx.add.limits')} hint={t('evx.add.limitsHint')} rows={3} value={limits}
        error={errors.limits} onChange={(e) => setLimits(e.target.value)} />
      {failure && <StatusMessage tone="error" title={t('evx.add.error')}>{failure}</StatusMessage>}
      <div className="actions">
        <Button type="submit" busy={busy}>{t('evx.add.save')}</Button>
        <Button variant="text" onClick={onCancel}>{t('evx.add.back')}</Button>
      </div>
    </form>
  );
}
