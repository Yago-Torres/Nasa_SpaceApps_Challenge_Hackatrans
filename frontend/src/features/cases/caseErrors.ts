import { ApiError } from '../../api/client';
import type { MessageKey } from '../../i18n/messages';

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/** Human message for a failed case/account request. 409/422 keep the server detail (it says what to fix). */
export function caseErrorText(error: unknown, t: T): string {
  if (!(error instanceof ApiError)) return t('state.unknownError');
  if (error.isNetwork) return t('state.networkError');
  if (error.status === 503) return t('cases.storageUnavailable');
  if (error.status === 401) return t('auth.sessionEnded');
  if (error.status === 403) return t('cases.forbidden');
  return error.message;
}

export const isStorageUnavailable = (error: unknown) => error instanceof ApiError && error.status === 503;
export const isUnauthorized = (error: unknown) => error instanceof ApiError && error.status === 401;
