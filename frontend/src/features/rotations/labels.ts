/**
 * `useI18n().t` takes a `MessageKey` literal so a typo fails `npm run build` (i18n/I18n.tsx).
 * The rotation comparator renders many backend enum codes (transition/constraint/screening
 * status, strategy kind, priority criterion, water regime, season role, market status…) as
 * short badges. Rather than writing one `MessageKey`-typed branch per enum value, every such
 * code is translated under the single flat key `rot.enum.<CODE>` (i18n/messages.ts) and looked
 * up through this one typed cast point, so a missing translation is caught in one place.
 */
import type { MessageKey } from '../../i18n/messages';

export function rotEnum(code: string): MessageKey {
  return `rot.enum.${code}` as MessageKey;
}
