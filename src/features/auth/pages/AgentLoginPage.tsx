import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link } from 'react-router';
import { useAuth } from '@/app/auth/useAuth';
import { AuthSplitLayout } from '@/app/shell/AuthSplitLayout';
import { Alert } from '@/components/feedback/Alert';
import { Button, FormField, Input } from '@/components/ui';
import { authApi } from '@/features/auth/api';
import { PasswordInput } from '@/features/auth/components/PasswordInput';
import { ThrottleNotice } from '@/features/auth/components/ThrottleNotice';
import { useSubmitError } from '@/features/auth/useSubmitError';
import { isApiError } from '@/services/api/errors';

const schema = z.object({
  username: z.string().trim().min(1, 'Enter your username'),
  password: z.string().min(1, 'Enter your password'),
});
type FormValues = z.infer<typeof schema>;

export default function AgentLoginPage() {
  const { signIn } = useAuth();
  const submitError = useSubmitError();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { username: '', password: '' },
  });

  useEffect(() => {
    document.title = 'Agent sign in · Yarotech RADIUS';
  }, []);

  const onSubmit = form.handleSubmit(async (values) => {
    submitError.reset();
    try {
      const tokens = await authApi.agentLogin(values.username, values.password);
      await signIn(tokens); // RedirectIfAuthenticated performs the navigation
    } catch (error) {
      if (isApiError(error) && error.status === 401) {
        submitError.setMessage('Incorrect username or password.');
        return;
      }
      if (isApiError(error) && error.status === 403) {
        submitError.setMessage(
          /not active/i.test(error.message)
            ? 'Your agent account is not active yet. Ask the business that registered you to approve it.'
            : 'This is not an agent account. Use the main sign in instead.',
        );
        return;
      }
      submitError.capture(error);
    }
  });

  return (
    <AuthSplitLayout
      title="Agent sign in"
      description="Sell vouchers and manage your wallet."
      panelTitle="Sell Wi-Fi anywhere"
      panelDescription="Check wallet balance, sell access codes and track commissions from the agent portal."
      panelPoints={[
        'Instant voucher sales with live wallet balance',
        'Commission tracking on every sale',
        'Works on any device — phone, tablet or desktop',
      ]}
      footer={
        <>
          Not an agent?{' '}
          <Link to="/login" className="font-medium text-brand-600 hover:underline">
            Sign in to a workspace
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} noValidate className="space-y-4">
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
    </AuthSplitLayout>
  );
}
