import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { CheckCircle2, PlayCircle, XCircle } from 'lucide-react';
import { Button, FormField, Input, PasswordInput } from '@/components/ui';
import { Alert } from '@/components/feedback';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { isApiError } from '@/services/api/errors';
import type { NasDevice } from '@/types/api';
import { useRadiusTest } from '../queries';
import { radiusTestSchema, type RadiusTestInput } from '../routerSchemas';

type Outcome = { passed: boolean } | null;

export function RadiusTestPanel({ router, canManage }: { router: NasDevice; canManage: boolean }) {
  const test = useRadiusTest();
  const form = useForm<RadiusTestInput>({
    resolver: zodResolver(radiusTestSchema),
    defaultValues: { username: '', password: '' },
    mode: 'onTouched',
  });
  const {
    message,
    reset: resetErrors,
    captureError,
  } = useFormSubmit(form.setError, ['username', 'password'] as const);
  const [outcome, setOutcome] = useState<Outcome>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [cooldown, setCooldown] = useCooldown();

  const submit = form.handleSubmit(async (values) => {
    resetErrors();
    setUnavailable(false);
    setOutcome(null);
    try {
      const result = await test.mutateAsync({ id: router.id, payload: values });
      setOutcome({ passed: result.passed });
      form.resetField('password');
    } catch (error) {
      if (isApiError(error) && error.status === 503) setUnavailable(true);
      else if (isApiError(error) && error.status === 429)
        setCooldown(error.retryAfterSeconds ?? 60);
      else captureError(error);
    }
  });

  if (!canManage)
    return (
      <p className="text-sm text-ink-600">
        Only managers can run RADIUS tests. Test results are recorded under Checks.
      </p>
    );

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,28rem)_1fr]">
      <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-4">
        <p className="text-sm text-ink-600">
          Sends an Access-Request to FreeRADIUS from {router.name}'s point of view. Use any voucher
          code or a test account. Limited to 10 tests per minute.
        </p>
        {message && <Alert tone="danger">{message}</Alert>}
        {unavailable && (
          <Alert tone="warning" title="RADIUS service unavailable">
            The authentication service did not respond. Nothing was recorded — try again in a
            moment.
          </Alert>
        )}
        {cooldown > 0 && (
          <Alert tone="info">Too many tests. You can run another in {cooldown}s.</Alert>
        )}
        <FormField label="Username" required error={form.formState.errors.username?.message}>
          <Input
            autoComplete="off"
            spellCheck={false}
            className="font-mono"
            {...form.register('username')}
          />
        </FormField>
        <FormField label="Password" required error={form.formState.errors.password?.message}>
          <PasswordInput autoComplete="off" className="font-mono" {...form.register('password')} />
        </FormField>
        <div>
          <Button
            type="submit"
            leadingIcon={<PlayCircle className="h-4 w-4" aria-hidden />}
            loading={form.formState.isSubmitting}
            disabled={cooldown > 0}
          >
            Run test
          </Button>
        </div>
      </form>
      <div aria-live="polite">
        {outcome && (
          <div
            className={`rounded-card border p-5 ${outcome.passed ? 'border-success-100 bg-success-50' : 'border-danger-100 bg-danger-50'}`}
          >
            <div className="flex items-center gap-2">
              {outcome.passed ? (
                <CheckCircle2 className="h-6 w-6 text-success-600" aria-hidden />
              ) : (
                <XCircle className="h-6 w-6 text-danger-600" aria-hidden />
              )}
              <h3
                className={`text-base font-semibold ${outcome.passed ? 'text-success-700' : 'text-danger-700'}`}
              >
                {outcome.passed ? 'Access accepted' : 'Access rejected'}
              </h3>
            </div>
            <p className="mt-2 text-sm text-ink-700">
              {outcome.passed
                ? 'FreeRADIUS accepted the credentials for this router. The radius_auth check has been recorded as passed.'
                : 'FreeRADIUS rejected the credentials. Check the voucher status, the plan limits, and that the router shared secret matches.'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

/** Seconds remaining before another attempt is allowed; ticks down once a second. */
function useCooldown() {
  const [remaining, setRemaining] = useState(0);
  useEffect(() => {
    if (remaining <= 0) return;
    const id = window.setTimeout(() => setRemaining((r) => r - 1), 1000);
    return () => window.clearTimeout(id);
  }, [remaining]);
  return [remaining, setRemaining] as const;
}
