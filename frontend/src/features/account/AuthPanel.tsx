import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { ApiError, authApi } from '../../api/client';
import { setSession } from '../../api/session';
import { Button, Field, StatusMessage } from '../../design/components';
import { useI18n } from '../../i18n/I18n';
import type { Lang } from '../../i18n/messages';

type Mode = 'signin' | 'signup';
type Problem = 'email' | 'password' | 'name';
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function waitText(seconds: number, lang: Lang): string {
  const locale = lang === 'es' ? 'es-ES' : 'en-GB';
  const [value, unit] = seconds < 60 ? [seconds, 'second'] : [Math.ceil(seconds / 60), 'minute'];
  return new Intl.NumberFormat(locale, { style: 'unit', unit, unitDisplay: 'long' }).format(value);
}

/**
 * Sign in / create account (ABB-05). Keeps everything typed when a request fails. The token
 * goes to api/session (memory + this tab's sessionStorage), never to localStorage.
 * `primary=false` when the surrounding view already has its primary action (wizard).
 */
export function AuthPanel({ notice, primary = true }: { notice?: string; primary?: boolean }) {
  const { t, lang } = useI18n();
  const headingId = useId();
  const [mode, setMode] = useState<Mode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [problems, setProblems] = useState<Problem[]>([]);
  const [failure, setFailure] = useState<{ title: string; body?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const form = useRef<HTMLFormElement>(null);
  const [focusRequest, setFocusRequest] = useState<{ field: Problem } | null>(null);

  // Focus the first invalid field right after the render that shows its error.
  useEffect(() => {
    if (focusRequest) form.current?.querySelector<HTMLElement>(`[data-field="${focusRequest.field}"]`)?.focus();
  }, [focusRequest]);

  function check(): Problem[] {
    const out: Problem[] = [];
    if (mode === 'signup' && (!name.trim() || name.trim().length > 160)) out.push('name');
    if (!EMAIL.test(email.trim())) out.push('email');
    if (mode === 'signin' ? !password : password.length < 12 || password.length > 256) out.push('password');
    return out;
  }

  function explain(err: unknown) {
    if (!(err instanceof ApiError)) return setFailure({ title: t('state.unknownError') });
    if (err.isNetwork) return setFailure({ title: t('state.networkError') });
    if (err.status === 503) return setFailure({ title: t('cases.storageUnavailable'), body: t('cases.storageUnavailableBody') });
    if (err.status === 401) return setFailure({ title: t('auth.invalid') });
    if (err.status === 409) return setFailure({ title: t('auth.exists') });
    if (err.status === 429) {
      return setFailure({ title: err.retryAfter ? t('auth.locked', { time: waitText(err.retryAfter, lang) }) : t('auth.lockedUnknown') });
    }
    setFailure({ title: err.message });
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const found = check();
    setProblems(found);
    setFailure(null);
    if (found.length) {
      setFocusRequest({ field: found[0] });
      return;
    }
    setBusy(true);
    try {
      if (mode === 'signup') await authApi.register({ email: email.trim(), password, display_name: name.trim() });
      setSession(await authApi.login({ email: email.trim(), password }));
    } catch (err) {
      explain(err);
    } finally {
      setBusy(false);
    }
  }

  function switchMode() {
    setMode((m) => (m === 'signin' ? 'signup' : 'signin'));
    setProblems([]);
    setFailure(null);
  }

  const has = (p: Problem) => problems.includes(p);
  return (
    <section className="panel auth" aria-labelledby={headingId}>
      <div className="section-head">
        <h2 id={headingId}>{mode === 'signin' ? t('auth.signInTitle') : t('auth.signUpTitle')}</h2>
        <p>{t('auth.lead')}</p>
      </div>
      {notice && <StatusMessage tone="partial" title={notice} />}
      <form ref={form} className="auth-form" noValidate onSubmit={submit}>
        {mode === 'signup' && (
          <Field label={t('auth.displayName')} name="display_name" data-field="name" autoComplete="name" value={name} maxLength={160}
            hint={t('auth.displayNameHint')} error={has('name') ? t('auth.nameError') : undefined}
            onChange={(e) => setName(e.target.value)} />
        )}
        <Field label={t('auth.email')} name="email" type="email" data-field="email" autoComplete="email" inputMode="email" spellCheck={false} value={email}
          maxLength={320} error={has('email') ? t('auth.emailError') : undefined} onChange={(e) => setEmail(e.target.value)} />
        <Field label={t('auth.password')} name="password" type="password" data-field="password" value={password} maxLength={256}
          autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
          hint={mode === 'signup' ? t('auth.passwordHint') : undefined}
          error={has('password') ? t(mode === 'signin' ? 'auth.passwordError' : 'auth.passwordLength') : undefined}
          onChange={(e) => setPassword(e.target.value)} />
        {failure && <StatusMessage tone="error" title={failure.title}>{failure.body}</StatusMessage>}
        <div className="actions">
          <Button type="submit" variant={primary ? 'primary' : 'secondary'} busy={busy}>
            {mode === 'signin' ? (busy ? t('auth.signingIn') : t('auth.signIn')) : busy ? t('auth.creating') : t('auth.createAccount')}
          </Button>
          <Button variant="text" onClick={switchMode}>{mode === 'signin' ? t('auth.toSignUp') : t('auth.toSignIn')}</Button>
        </div>
        <p className="muted">{t('auth.sessionNote')}</p>
      </form>
    </section>
  );
}
