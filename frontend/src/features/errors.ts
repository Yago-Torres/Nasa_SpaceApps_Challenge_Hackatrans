import { ApiError } from '../api/client';
import type { MessageKey } from '../i18n/messages';

/** Human message for a failed request: network problems get a fixed sentence, HTTP errors keep the backend detail. */
export function errorText(error: unknown, t: (key: MessageKey) => string): string {
  if (error instanceof ApiError) return error.isNetwork ? t('state.networkError') : error.message;
  return t('state.unknownError');
}
