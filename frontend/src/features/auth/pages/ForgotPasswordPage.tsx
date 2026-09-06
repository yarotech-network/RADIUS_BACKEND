import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link } from 'react-router';
import { MailCheck } from 'lucide-react';
import { AuthCard } from '@/app/shell/AuthCard';
import { Alert } from '@/components/feedback/Alert';
import { EmptyState } from '@/components/feedback/EmptyState';
import { Button, FormField, Input } from '@/components/ui';
import { accountApi } from '@/features/auth/api';
import { ThrottleNotice } from '@/features/auth/components/ThrottleNotice';
import { useSubmitError } from '@/features/auth/useSubmitError';
import { emailSchema } from '@/lib/validation/schemas';
import { applyApiErrors } from '@/lib/validation/applyApiErrors';

const schema = z.object({ email: emailSchema });
type FormValues = z.infer<typeof schema>;

export default function ForgotPasswordPage() {
  const [sent, setSent] = useState<string | null>(null);
  const submitError = useSubmitError();
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { email: '' } });

  useEffect(() => {
    document.title = 'Reset password · Yarotech RADIUS';
  }, []);

  const onSubmit = form.handleSubmit(async (values) => {
    submitError.reset();
    try {
      await accountApi.requestPasswordReset(values);
      setSent(values.email);
    } catch (error) {
      const leftover = applyApiErrors(error, form.setError, ['email']);
      if (leftover) submitError.capture(error);
    }
  });

  if (sent) {
    return (
      <AuthCard
        title="Check your email"
        footer={
          <Link to="/login" className="font-medium text-brand-600 hover:underline">
            Back to sign in
          </Link>
        }
      >
        <EmptyState
          icon={<MailCheck />}
          title="If an account exists, we sent a link"
          description={`Instructions were sent to ${sent} if an active account uses that address. The link expires after a short while.`}
          compact
          action={
            <Button variant="secondary" size="sm" onClick={() => setSent(null)}>
              Use a different email
            </Button>
          }
        />
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Forgot your password?"
      description="Enter your account email and we will send a reset link."
      footer={
        <Link to="/login" className="font-medium text-brand-600 hover:underline">
          Back to sign in
        </Link>
      }
    >
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        {submitError.message && <Alert tone="danger">{submitError.message}</Alert>}
        {submitError.retryAfter !== null && (
          <ThrottleNotice seconds={submitError.retryAfter} onDone={submitError.clearThrottle} />
        )}
        <FormField label="Email" error={form.formState.errors.email?.message} required>
          <Input
            type="email"
            inputMode="email"
            autoComplete="email"
            autoFocus
            {...form.register('email')}
          />
        </FormField>
        <Button
          type="submit"
          block
          size="lg"
          loading={form.formState.isSubmitting}
          disabled={submitError.retryAfter !== null && submitError.retryAfter > 0}
        >
          Send reset link
        </Button>
      </form>
    </AuthCard>
  );
}
