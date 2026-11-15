import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { messages, type Lang, type MessageKey } from './messages';

type Vars = Record<string, string | number>;
type I18n = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: MessageKey, vars?: Vars) => string;
  /** Locale-aware number with a true minus sign; `signed` adds "+" to positives. */
  num: (value: number, options?: { digits?: number; signed?: boolean }) => string;
};

const STORAGE_KEY = 'abb-lang';
const Ctx = createContext<I18n | null>(null);

export function interpolate(template: string, vars?: Vars): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (name in vars ? String(vars[name]) : match));
}

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'en' || saved === 'es') return saved;
  } catch {
    /* storage unavailable: fall through */
  }
  const preferred = typeof navigator !== 'undefined' ? navigator.languages ?? [navigator.language] : [];
  return preferred.some((l) => l?.toLowerCase().startsWith('es')) ? 'es' : 'en';
}

export function I18nProvider({ children, lang: forced }: { children: ReactNode; lang?: Lang }) {
  const [lang, setLangState] = useState<Lang>(forced ?? initialLang);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.title = messages[lang]['app.docTitle'];
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo<I18n>(() => {
    const locale = lang === 'es' ? 'es-ES' : 'en-GB';
    return {
      lang,
      setLang,
      t: (key, vars) => interpolate(messages[lang][key], vars),
      num: (value, options = {}) =>
        new Intl.NumberFormat(locale, {
          minimumFractionDigits: options.digits ?? 0,
          maximumFractionDigits: options.digits ?? 0,
          signDisplay: options.signed ? 'exceptZero' : 'auto',
        })
          .format(value)
          .replace('-', '−'),
    };
  }, [lang, setLang]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useI18n must be used inside <I18nProvider>');
  return ctx;
}
