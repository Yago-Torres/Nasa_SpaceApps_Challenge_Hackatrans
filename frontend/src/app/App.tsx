import { useEffect, useRef, useState, type ReactElement } from 'react';
import { Menu, X } from 'lucide-react';
import { useI18n } from '../i18n/I18n';
import type { Lang } from '../i18n/messages';
import { LegendSprite } from '../design/components';
import { ROUTES, hrefFor, useRoute, useSharedToken, type RouteId } from './routes';
import { InvestigationProvider } from './investigation';
import { Dashboard } from '../features/Dashboard';
import { Cases } from '../features/Cases';
import { Investigation } from '../features/Investigation';
import { Evidence } from '../features/Evidence';
import { Rotations } from '../features/Rotations';
import { Collaboration } from '../features/Collaboration';
import { Report } from '../features/Report';
import { SharedCase } from '../features/SharedCase';
import { AccountStatus } from '../features/account/AccountStatus';

const SCREENS: Record<RouteId, () => ReactElement> = {
  dashboard: Dashboard,
  cases: Cases,
  investigation: Investigation,
  evidence: Evidence,
  rotations: Rotations,
  collaboration: Collaboration,
  report: Report,
};

function Mark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="2.5" y="2.5" width="19" height="19" rx="3" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M2.5 15c4-1 6-5 9.5-5s5.5 3 9.5 2.5" fill="none" stroke="currentColor" strokeWidth="2" />
      <circle cx="16.5" cy="7.5" r="2.2" fill="currentColor" />
    </svg>
  );
}

export function App() {
  const { t, lang, setLang } = useI18n();
  const route = useRoute();
  const sharedToken = useSharedToken();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const firstRender = useRef(true);
  const Screen = SCREENS[route];
  const current = ROUTES.find((r) => r.id === route)!;
  const pageLabel = sharedToken ? 'shared.title' : current.label;

  // On navigation: close the mobile menu, update the title and move focus to the page heading.
  useEffect(() => {
    setMenuOpen(false);
    document.title = `${t(pageLabel)} · ${t('app.name')}`;
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    window.scrollTo({ top: 0 });
    document.querySelector<HTMLElement>('[data-page-title]')?.focus();
  }, [route, sharedToken]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    document.title = `${t(pageLabel)} · ${t('app.name')}`;
  }, [lang, pageLabel, t]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setMenuOpen(false);
        menuButton.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  return (
    <InvestigationProvider>
      <LegendSprite />
      <a className="skip" href="#content">{t('app.skip')}</a>
      <div className={`shell${menuOpen ? ' menu-open' : ''}`}>
        <header className="topbar">
          <a className="brand" href={hrefFor('dashboard')}><Mark /><span translate="no">{t('app.name')}</span></a>
          <button ref={menuButton} type="button" className="btn btn--secondary" aria-expanded={menuOpen} aria-controls="rail" onClick={() => setMenuOpen((o) => !o)}>
            {menuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
            <span>{t('app.menu')}</span>
          </button>
        </header>

        <nav className="rail" id="rail" aria-label={t('app.navLabel')}>
          <a className="brand" href={hrefFor('dashboard')}><Mark /><span translate="no">{t('app.name')}</span></a>
          <p className="dev">{t('app.devBuild')}</p>
          <ol className="nav">
            {ROUTES.map((r, i) => (
              <li key={r.id} className={r.available ? undefined : 'pending'}>
                <a href={hrefFor(r.id)} aria-current={!sharedToken && r.id === route ? 'page' : undefined}>
                  <span className="n" aria-hidden="true">{i === 0 ? '·' : i}</span>
                  <span>{t(r.label)}</span>
                  {!r.available && <small>{t('nav.notBuilt')}</small>}
                </a>
              </li>
            ))}
          </ol>
          <div className="bottom">
            <AccountStatus />
            <div className="lang" role="group" aria-label={t('app.language')}>
              {(['en', 'es'] as Lang[]).map((l) => (
                <button key={l} type="button" aria-pressed={lang === l} onClick={() => setLang(l)} lang={l}>
                  {l.toUpperCase()}
                </button>
              ))}
            </div>
            <p className="foot">{t('app.footer')}</p>
          </div>
        </nav>

        <main className="main" id="content" tabIndex={-1}>
          <div className="page">
            {sharedToken ? <SharedCase key={sharedToken} token={sharedToken} /> : <Screen />}
          </div>
        </main>
      </div>
    </InvestigationProvider>
  );
}
