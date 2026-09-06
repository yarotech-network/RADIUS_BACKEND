import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link } from 'react-router';
import { useAuth } from '@/app/auth/useAuth';
import { AuthCard } from '@/app/shell/AuthCard';
import { Alert } from '@/components/feedback/Alert';
import { Button, FormField, Input } from '@/components/ui';
import { authApi } from '@/features/auth/api';
import { PasswordInput } from '@/features/auth/components/PasswordInput';
import { ThrottleNotice } from '@/features/auth/components/ThrottleNotice';
import { useSubmitError } from '@/features/auth/useSubmitError';
import { applyApiErrors } from '@/lib/validation/applyApiErrors';
import { isApiError } from '@/services/api/errors';

const schema = z.object({
  username: z.string().trim().min(1, 'Enter your username'),
  password: z.string().min(1, 'Enter your password'),
});
type FormValues = z.infer<typeof schema>;

export default function LoginPage() {
  const { signIn, signOutReason } = useAuth();
  const submitError = useSubmitError();

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { username: '', password: '' },
  });

  useEffect(() => {
    document.title = 'Sign in · Yarotech RADIUS';
  }, []);

  const onSubmit = form.handleSubmit(async (values) => {
    submitError.reset();
    try {
      const tokens = await authApi.login(values.username, values.password);
      await signIn(tokens); // RedirectIfAuthenticated performs the navigation
    } catch (error) {
      if (isApiError(error) && error.status === 401) {
        submitError.setMessage('Incorrect username or password.');
        return;
      }
      if (isApiError(error) && error.kind === 'validation') {
        const leftover = applyApiErrors(error, form.setError, ['username', 'password']);
        if (leftover) submitError.setMessage(leftover);
        return;
      }
      submitError.capture(error);
    }
  });

  return (
    <AuthCard
      title="Sign in"
      description="Manage your hotspot plans, vouchers and routers."
      footer={
        <>
          New here?{' '}
          <Link to="/register" className="font-medium text-brand-600 hover:underline">
            Create a workspace
          </Link>
          <span className="mx-2 text-ink-300">·</span>
          <Link to="/agent/login" className="font-medium text-brand-600 hover:underline">
            Agent sign in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        {signOutReason && !submitError.message && <Alert tone="info">{signOutReason}</Alert>}
        {submitError.message && <Alert tone="danger">{submitError.message}</Alert>}
        {submitError.retryAfter !== null && (
          <ThrottleNotice seconds={submitError.retryAfter} onDone={submitError.clearThrottle} />
        )}
        <FormField label="Username" error={form.formState.errors.username?.message} required>
          <Input
            autoComplete="username"
            autoFocus
            autoCapitalize="none"
            spellCheck={false}
            {...form.register('username')}
          />
        </FormField>
        <FormField label="Password" error={form.formState.errors.password?.message} required>
          <PasswordInput autoComplete="current-password" {...form.register('password')} />
        </FormField>
        <div className="flex items-center justify-end">
          <Link
            to="/forgot-password"
            className="text-sm font-medium text-brand-600 hover:underline"
          >
            Forgot password?
          </Link>
        </div>
        <Button
          type="submit"
          block
          size="lg"
          loading={form.formState.isSubmitting}
          disabled={submitError.retryAfter !== null && submitError.retryAfter > 0}
        >
          Sign in
        </Button>
      </form>
    </AuthCard>
  );
}
