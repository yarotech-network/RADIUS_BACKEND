import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { KeyRound } from 'lucide-react';
import { AuthCard } from '@/app/shell/AuthCard';
import { Alert } from '@/components/feedback/Alert';
import { EmptyState } from '@/components/feedback/EmptyState';
import { Button, FormField } from '@/components/ui';
import { accountApi } from '@/features/auth/api';
import { PasswordInput } from '@/features/auth/components/PasswordInput';
import { useSubmitError } from '@/features/auth/useSubmitError';
import { applyApiErrors } from '@/lib/validation/applyApiErrors';
import { passwordPairRefinement, passwordPairShape } from '@/lib/validation/schemas';

const schema = z
  .object(passwordPairShape)
  .refine(passwordPairRefinement.check, passwordPairRefinement.options);
type FormValues = z.infer<typeof schema>;

export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const uid = params.get('uid') ?? '';
  const token = params.get('token') ?? '';
  const [done, setDone] = useState(false);
  const submitError = useSubmitError();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { password: '', password_confirm: '' },
  });

  useEffect(() => {
    document.title = 'Choose a new password · Yarotech RADIUS';
  }, []);

  if (!uid || !token) {
    return (
      <AuthCard
        title="Invalid reset link"
        footer={
          <Link to="/forgot-password" className="font-medium text-brand-600 hover:underline">
            Request a new link
          </Link>
        }
      >
        <Alert tone="danger">
          This link is missing its security token. Open the link from your email again, or request a
          new one.
        </Alert>
      </AuthCard>
    );
  }

  if (done) {
    return (
      <AuthCard title="Password updated">
        <EmptyState
          icon={<KeyRound />}
          title="You can sign in now"
          description="All previous sessions were signed out for security."
          compact
          action={
            <Button onClick={() => navigate('/login', { replace: true })}>Go to sign in</Button>
          }
        />
      </AuthCard>
    );
  }

  const onSubmit = form.handleSubmit(async (values) => {
    submitError.reset();
    try {
      await accountApi.confirmPasswordReset({ uid, token, ...values });
      setDone(true);
    } catch (error) {
      const leftover = applyApiErrors(error, form.setError, ['password', 'password_confirm'], {
        new_password: 'password',
      });
      if (leftover)
        submitError.setMessage(
          /invalid|expired/i.test(leftover)
            ? 'This reset link is invalid or has expired. Request a new one.'
            : leftover,
        );
    }
  });

  return (
    <AuthCard
      title="Choose a new password"
      footer={
        <Link to="/login" className="font-medium text-brand-600 hover:underline">
          Back to sign in
        </Link>
      }
    >
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        {submitError.message && <Alert tone="danger">{submitError.message}</Alert>}
        <FormField
          label="New password"
          error={form.formState.errors.password?.message}
          hint="At least 8 characters, not only numbers."
          required
        >
          <PasswordInput autoComplete="new-password" autoFocus {...form.register('password')} />
        </FormField>
        <FormField
          label="Confirm new password"
          error={form.formState.errors.password_confirm?.message}
          required
        >
          <PasswordInput autoComplete="new-password" {...form.register('password_confirm')} />
        </FormField>
        <Button type="submit" block size="lg" loading={form.formState.isSubmitting}>
          Update password
        </Button>
      </form>
    </AuthCard>
  );
}
