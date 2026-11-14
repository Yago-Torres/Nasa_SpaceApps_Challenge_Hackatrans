import { useMemo } from 'react';
import { useI18n } from '../../../i18n/I18n';

/** Locale-aware date and date-time formatting for collaboration records (EN/ES). */
export function useDates() {
  const { lang } = useI18n();
  return useMemo(() => {
    const locale = lang === 'es' ? 'es-ES' : 'en-GB';
    const dateTime = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' });
    const date = new Intl.DateTimeFormat(locale, { dateStyle: 'medium' });
    return {
      dateTime: (iso: string) => dateTime.format(new Date(iso)),
      date: (iso: string) => date.format(new Date(iso.length === 10 ? `${iso}T00:00:00` : iso)),
    };
  }, [lang]);
}
