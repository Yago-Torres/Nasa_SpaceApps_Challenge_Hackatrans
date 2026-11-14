import { useCallback, useEffect, useState } from 'react';
import { Download, FilePlus2, ShieldCheck } from 'lucide-react';
import { useI18n } from '../../../i18n/I18n';
import { Button, StatusMessage } from '../../../design/components';
import { CaseGate } from '../CaseGate';
import { CaseTitleBlock } from '../CaseTitleBlock';
import { caseErrorText } from '../caseErrors';
import { useDates } from '../collaboration/format';
import { reportsApi, type ReportFormat, type ReportView, type VerifyResult } from './reportApi';

const FORMATS: { id: ReportFormat; label: 'rep2.fmtMarkdown' | 'rep2.fmtHtml' | 'rep2.fmtJson' | 'rep2.fmtPdf' }[] = [
  { id: 'markdown', label: 'rep2.fmtMarkdown' }, { id: 'html', label: 'rep2.fmtHtml' }, { id: 'json', label: 'rep2.fmtJson' }, { id: 'pdf', label: 'rep2.fmtPdf' },
];
const GENERATOR_ROLES = new Set(['OWNER', 'EDITOR', 'REVIEWER']);

function save(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Case "Report" tab (ABB-26): versioned, downloadable, verifiable case reports built by the server. */
export function CaseReport({ caseId }: { caseId: string }) {
  const { t } = useI18n();
  return (
    <CaseGate caseId={caseId} title={t('rep2.title')}>
      {(c) => (
        <>
          <CaseTitleBlock c={c} lead={t('rep2.lead')} />
          <Versions caseId={caseId} canGenerate={!c.server || GENERATOR_ROLES.has(c.server.myRole)} />
        </>
      )}
    </CaseGate>
  );
}

function Versions({ caseId, canGenerate }: { caseId: string; canGenerate: boolean }) {
  const { t } = useI18n();
  const dates = useDates();
  const [items, setItems] = useState<ReportView[] | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const [verified, setVerified] = useState<Record<number, VerifyResult>>({});

  const load = useCallback(() => {
    const controller = new AbortController();
    reportsApi.list(caseId, controller.signal).then(setItems, (err) => {
      if (err?.name !== 'AbortError') setError(caseErrorText(err, t));
    });
    return () => controller.abort();
  }, [caseId, t]);
  useEffect(() => load(), [load]);

  async function run(key: string, work: () => Promise<void>) {
    setBusy(key); setError(''); setNotice('');
    try { await work(); } catch (err) { setError(caseErrorText(err, t)); } finally { setBusy(null); }
  }

  const generate = () => run('new', async () => {
    const created = await reportsApi.create(caseId);
    setItems(await reportsApi.list(caseId));
    setNotice(t('rep2.created', { n: created.version }));
  });
  const download = (r: ReportView, format: ReportFormat) => run(`${r.version}:${format}`, async () => {
    const out = await reportsApi.download(caseId, r.version, format);
    save(out.blob, out.filename);
    setNotice(t('rep2.downloaded', { file: out.filename }));
  });
  const verify = (r: ReportView) => run(`${r.version}:verify`, async () => {
    const result = await reportsApi.verify(caseId, r.version);
    setVerified((v) => ({ ...v, [r.version]: result }));
  });

  return (
    <section className="panel" aria-labelledby="rep2-versions">
      <div className="panel-head">
        <h2 id="rep2-versions">{t('rep2.versions')}</h2>
        {canGenerate && (
          <Button variant="primary" busy={busy === 'new'} icon={<FilePlus2 aria-hidden="true" />} onClick={generate}>
            {busy === 'new' ? t('rep2.generating') : t('rep2.generate')}
          </Button>
        )}
      </div>
      {!canGenerate && <p className="muted">{t('rep2.readOnly')}</p>}
      {error && <StatusMessage tone="error" title={t('rep2.error')} action={<Button onClick={load}>{t('state.retry')}</Button>}>{error}</StatusMessage>}
      {notice && <StatusMessage tone="ok" title={notice} />}
      {!items && !error && <StatusMessage tone="loading" title={t('rep2.loading')} />}
      {items?.length === 0 && <StatusMessage tone="empty" title={t('rep2.empty')}>{t('rep2.emptyBody')}</StatusMessage>}
      {items?.map((r) => (
        <article key={r.id} className="panel" aria-labelledby={`rep2-v${r.version}`}>
          <h3 id={`rep2-v${r.version}`}>{t('rep2.version', { n: r.version })}</h3>
          <dl className="kv">
            <div><dt>{t('rep2.generatedAt')}</dt><dd>{dates.dateTime(r.generated_at)}</dd></div>
            <div><dt>{t('rep2.by')}</dt><dd>{r.generated_by?.display_name ?? t('rep2.unknownAuthor')}</dd></div>
            <div><dt>{t('rep2.caseVersion')}</dt><dd>{r.case_version ?? '—'}</dd></div>
            <div><dt>{t('rep2.status')}</dt><dd>{t('rep2.preliminary')}</dd></div>
            <div><dt>{t('rep2.hash')}</dt><dd><code title={r.checksum_sha256 ?? ''}>{r.checksum_sha256?.slice(0, 16)}…</code></dd></div>
            <div><dt>{t('rep2.sourceHash')}</dt><dd><code title={r.sources_sha256 ?? ''}>{r.sources_sha256?.slice(0, 16)}…</code> ({t('rep2.sources', { n: r.source_manifest_ids.length })})</dd></div>
          </dl>
          <h4>{t('rep2.changes')}</h4>
          {r.changes?.initial !== false ? <p>{t('rep2.initial')}</p>
            : r.changes.items.length === 0 ? <p>{t('rep2.noChanges', { n: r.changes.previous_version ?? '—' })}</p>
            : (
              <div className="table-wrap">
                <table className="data">
                  <caption className="sr-only">{t('rep2.changesCaption', { n: r.changes.previous_version ?? '—' })}</caption>
                  <thead><tr><th scope="col">{t('rep2.section')}</th><th scope="col">{t('rep2.change')}</th><th scope="col">{t('rep2.record')}</th></tr></thead>
                  <tbody>{r.changes.items.map((i) => <tr key={`${i.section}:${i.id}`}><td>{i.section}</td><td>{i.change}</td><td>{i.label}</td></tr>)}</tbody>
                </table>
              </div>
            )}
          <div className="actions">
            {FORMATS.filter((f) => r.formats.includes(f.id)).map((f) => (
              <Button key={f.id} variant="secondary" busy={busy === `${r.version}:${f.id}`} icon={<Download aria-hidden="true" />} onClick={() => download(r, f.id)}>
                {t(f.label)}
              </Button>
            ))}
            <Button variant="secondary" busy={busy === `${r.version}:verify`} icon={<ShieldCheck aria-hidden="true" />} onClick={() => verify(r)}>{t('rep2.verify')}</Button>
          </div>
          {verified[r.version] && (
            <StatusMessage tone={verified[r.version].valid ? 'ok' : 'error'} title={verified[r.version].valid ? t('rep2.verifyOk') : t('rep2.verifyBad')}>
              {verified[r.version].detail}
            </StatusMessage>
          )}
        </article>
      ))}
      <p className="muted">{t('rep2.pdfNote')}</p>
      <p className="muted">{t('rep2.privacyNote')}</p>
    </section>
  );
}
