import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { BadgeCheck } from 'lucide-react';
import { useAuth } from '@/app/auth/useAuth';
import { AuthCard } from '@/app/shell/AuthCard';
import { Alert } from '@/components/feedback/Alert';
import { EmptyState } from '@/components/feedback/EmptyState';
import { Button, FormField, Input } from '@/components/ui';
import { accountApi, authApi } from '@/features/auth/api';
import { PasswordInput } from '@/features/auth/components/PasswordInput';
import { useSubmitError } from '@/features/auth/useSubmitError';
import { applyApiErrors } from '@/lib/validation/applyApiErrors';
import {
  passwordPairRefinement,
  passwordPairShape,
  usernameSchema,
} from '@/lib/validation/schemas';
import { displayName } from '@/services/auth/principal';

const schema = z
  .object({ username: usernameSchema, ...passwordPairShape })
  .refine(passwordPairRefinement.check, passwordPairRefinement.options);
type FormValues = z.infer<typeof schema>;

/**
 * `/accept-invitation?token=…` — platform-staff invitation.
 * Anonymous visitors create a new account (username + password) in the same call; signed-in users
 * link the invitation to their current account (the backend checks the email matches).
 */
export default function AcceptInvitationPage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const { status, principal, signIn, refreshPrincipal, signOut } = useAuth();
  const navigate = useNavigate();
  const [accepted, setAccepted] = useState(false);
  const submitError = useSubmitError();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { username: '', password: '', password_confirm: '' },
  });

  useEffect(() => {
    document.title = 'Accept invitation · Yarotech RADIUS';
  }, []);

  if (!token) {
    return (
      <AuthCard title="Invalid invitation link">
        <Alert tone="danger">
          This link is missing its invitation token. Ask the administrator to send the link again.
        </Alert>
      </AuthCard>
    );
  }

  if (accepted) {
    return (
      <AuthCard title="Invitation accepted">
        <EmptyState
          icon={<BadgeCheck />}
          title="You now have staff access"
          description="Choose the tenant you want to work on to get started."
          compact
          action={
            <Button onClick={() => navigate('/select-tenant', { replace: true })}>Continue</Button>
          }
        />
      </AuthCard>
    );
  }

  const signedIn = status === 'authenticated' && principal;

  const acceptAsCurrentUser = async () => {
    submitError.reset();
    try {
      await accountApi.acceptInvitation({ token }, false);
      await refreshPrincipal();
      setAccepted(true);
    } catch (error) {
      submitError.capture(error);
    }
  };

  const onSubmit = form.handleSubmit(async (values) => {
    submitError.reset();
    try {
      await accountApi.acceptInvitation(
        { token, username: values.username, password: values.password },
        true,
      );
      // The accept endpoint does not return tokens — sign in with the new credentials.
      const tokens = await authApi.login(values.username, values.password);
      await signIn(tokens);
      setAccepted(true);
    } catch (error) {
      const leftover = applyApiErrors(error, form.setError, [
        'username',
        'password',
        'password_confirm',
      ]);
      if (leftover) submitError.setMessage(leftover);
    }
  });

  if (signedIn) {
    return (
      <AuthCard
        title="Accept staff invitation"
        description={`You are signed in as ${displayName(principal.user)} (${principal.user.email}).`}
      >
        <div className="space-y-4">
          {submitError.message && <Alert tone="danger">{submitError.message}</Alert>}
          <Alert tone="info">
            The invitation must have been sent to the email address of this account. If it was sent
            to a different address, sign out and open the link again.
          </Alert>
          <Button block size="lg" onClick={acceptAsCurrentUser}>
            Accept invitation
          </Button>
          <Button block variant="ghost" onClick={() => void signOut()}>
            Sign out and use a different account
          </Button>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Accept staff invitation"
      description="Create your account to accept. The email address is taken from the invitation."
      footer={
        <>
          Already have an account?{' '}
          <Link
            to="/login"
            state={{ from: `/accept-invitation?token=${encodeURIComponent(token)}` }}
            className="font-medium text-brand-600 hover:underline"
          >
            Sign in first
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        {submitError.message && <Alert tone="danger">{submitError.message}</Alert>}
        <FormField label="Username" error={form.formState.errors.username?.message} required>
          <Input
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            autoFocus
            {...form.register('username')}
          />
        </FormField>
        <FormField
          label="Password"
          error={form.formState.errors.password?.message}
          hint="At least 8 characters, not only numbers."
          required
        >
          <PasswordInput autoComplete="new-password" {...form.register('password')} />
        </FormField>
        <FormField
          label="Confirm password"
          error={form.formState.errors.password_confirm?.message}
          required
        >
          <PasswordInput autoComplete="new-password" {...form.register('password_confirm')} />
        </FormField>
        <Button type="submit" block size="lg" loading={form.formState.isSubmitting}>
          Create account & accept
        </Button>
      </form>
    </AuthCard>
  );
}
