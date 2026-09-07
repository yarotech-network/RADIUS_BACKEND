import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router';
import { MailCheck } from 'lucide-react';
import { useAuth } from '@/app/auth/useAuth';
import { AuthSplitLayout } from '@/app/shell/AuthSplitLayout';
import { Alert } from '@/components/feedback/Alert';
import { Button, FormField, Input } from '@/components/ui';
import { authApi } from '@/features/auth/api';
import { useSubmitError } from '@/features/auth/useSubmitError';
import { isApiError } from '@/services/api/errors';

const CODE_LENGTH = 6;
const RESEND_COOLDOWN_SECONDS = 60;

/**
 * `/verify-email` — enter the 6-digit OTP that was emailed after registration.
 * On success the account activates and the new owner is signed in immediately.
 */
export default function VerifyEmailPage({
  cooldownSeconds = RESEND_COOLDOWN_SECONDS,
}: {
  /** Overridable for tests; the route always uses the default. */
  cooldownSeconds?: number;
} = {}) {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { signIn } = useAuth();
  const submitError = useSubmitError();

  const stateEmail = (location.state as { email?: unknown } | null)?.email;
  const initialEmail =
    typeof stateEmail === 'string' && stateEmail.includes('@')
      ? stateEmail
      : (searchParams.get('email') ?? '');
  const [email, setEmail] = useState(initialEmail);
  const [digits, setDigits] = useState<string[]>(Array(CODE_LENGTH).fill(''));
  const [submitting, setSubmitting] = useState(false);
  const [resent, setResent] = useState(false);
  const [countdown, setCountdown] = useState(cooldownSeconds);
  const inputsRef = useRef<(HTMLInputElement | null)[]>([]);

  const trimmedEmail = email.trim();
  const joined = digits.join('');
  const codeComplete = joined.length === CODE_LENGTH && !digits.includes('');

  useEffect(() => {
    document.title = 'Verify your email · Yarotech RADIUS';
  }, []);

  useEffect(() => {
    if (!submitting && digits[0] === '') inputsRef.current[0]?.focus();
  }, [submitting, digits]);

  // Resend cooldown ticker — one interval for the page's lifetime; it parks at 0.
  useEffect(() => {
    const timer = setInterval(() => setCountdown((s) => (s > 0 ? s - 1 : 0)), 1000);
    return () => clearInterval(timer);
  }, []);

  const submitCode = async (value: string) => {
    if (!trimmedEmail) return;
    setSubmitting(true);
    submitError.reset();
    try {
      const tokens = await authApi.verifyEmail({ email: trimmedEmail, code: value });
      await signIn(tokens); // RedirectIfAuthenticated performs the navigation
    } catch (error) {
      setDigits(Array(CODE_LENGTH).fill(''));
      inputsRef.current[0]?.focus();
      if (isApiError(error) && (error.status === 400 || error.kind === 'validation')) {
        submitError.setMessage(error.message);
        return;
      }
      submitError.capture(error);
    } finally {
      setSubmitting(false);
    }
  };

  const setDigit = (index: number, raw: string) => {
    const value = raw.replace(/\D/g, '');
    if (!value) {
      setDigits((prev) => prev.map((d, i) => (i === index ? '' : d)));
      return;
    }
    // Typing or pasting one-or-more digits: fill from the current box onwards.
    const chars = value.split('');
    setDigits((prev) => {
      const next = [...prev];
      for (let i = 0; i < chars.length && index + i < CODE_LENGTH; i++) {
        next[index + i] = chars[i] ?? '';
      }
      const filled = next.join('');
      if (filled.length === CODE_LENGTH && !next.includes('')) {
        void submitCode(filled);
      } else {
        inputsRef.current[Math.min(index + chars.length, CODE_LENGTH - 1)]?.focus();
      }
      return next;
    });
  };

  const onKeyDown = (index: number, event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Backspace' && !digits[index] && index > 0) {
      event.preventDefault();
      setDigits((prev) => prev.map((d, i) => (i === index - 1 ? '' : d)));
      inputsRef.current[index - 1]?.focus();
    }
    if (event.key === 'ArrowLeft' && index > 0) inputsRef.current[index - 1]?.focus();
    if (event.key === 'ArrowRight' && index < CODE_LENGTH - 1)
      inputsRef.current[index + 1]?.focus();
  };

  const onResend = async () => {
    if (!trimmedEmail || countdown > 0) return;
    submitError.reset();
    setResent(false);
    try {
      await authApi.resendVerification(trimmedEmail);
      setResent(true);
      setCountdown(cooldownSeconds);
    } catch (error) {
      submitError.capture(error);
    }
  };

  return (
    <AuthSplitLayout
      title="Verify your email"
      description="Enter the 6-digit code we sent to finish activating your workspace."
      footer={
        <>
          Wrong address?{' '}
          <Link to="/register" className="font-medium text-brand-600 hover:underline">
            Register again
          </Link>{' '}
          with the correct email, or{' '}
          <Link to="/login" className="font-medium text-brand-600 hover:underline">
            sign in
          </Link>{' '}
          if you already verified.
        </>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (codeComplete) void submitCode(joined);
        }}
        noValidate
        className="space-y-4"
      >
        {submitError.message && <Alert tone="danger">{submitError.message}</Alert>}
        {resent && (
          <Alert tone="success">A new code is on its way. It can take a minute to arrive.</Alert>
        )}

        <FormField label="Email" required>
          <Input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={submitting}
          />
        </FormField>

        <FormField label="Verification code" required>
          <div className="flex gap-2" role="group" aria-label="6-digit verification code">
            {digits.map((digit, index) => (
              <input
                key={index}
                ref={(el) => {
                  inputsRef.current[index] = el;
                }}
                value={digit}
                onChange={(e) => setDigit(index, e.target.value)}
                onKeyDown={(e) => onKeyDown(index, e)}
                inputMode="numeric"
                autoComplete={index === 0 ? 'one-time-code' : 'off'}
                aria-label={`Digit ${index + 1} of ${CODE_LENGTH}`}
                maxLength={CODE_LENGTH}
                disabled={submitting}
                className="rounded-input h-12 w-full min-w-0 border border-border bg-surface text-center font-mono text-lg text-ink-900 tabular-nums focus:border-brand-500 focus:ring-2 focus:ring-brand-200 focus:outline-none"
              />
            ))}
          </div>
        </FormField>

        <Button type="submit" block size="lg" loading={submitting} disabled={!codeComplete}>
          <span className="inline-flex items-center gap-2">
            <MailCheck className="size-4" aria-hidden />
            Verify and continue
          </span>
        </Button>

        <div className="text-center text-sm text-ink-500">
          Didn&apos;t get the code?{' '}
          {countdown > 0 ? (
            <span className="text-ink-400 tabular-nums">Resend available in {countdown}s</span>
          ) : (
            <button
              type="button"
              onClick={() => void onResend()}
              className="font-medium text-brand-600 hover:underline"
            >
              Resend code
            </button>
          )}
        </div>
      </form>
    </AuthSplitLayout>
  );
}
