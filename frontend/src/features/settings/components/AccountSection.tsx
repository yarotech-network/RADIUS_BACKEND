import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button, CopyButton, DescriptionList, FormField, PasswordInput } from '@/components/ui';
import { Alert, useToast } from '@/components/feedback';
import { useAuth } from '@/app/auth/useAuth';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { accountApi, authApi } from '@/features/auth/api';
import {
  changePasswordSchema,
  type ChangePasswordInput,
  type ChangePasswordOutput,
} from '../settingsSchemas';
import { SettingsCard } from './SettingsCard';

const FIELDS = ['old_password', 'new_password', 'confirm'] as const;

/** Signed-in user's identity (with the numeric ID owners need to add them to a team) and password change. */
export function AccountSection() {
  const { principal } = useAuth();
  const user = principal?.user;
  const roleLabel = principal?.kind === 'member' ? principal.role : (user?.role ?? '');
  return (
    <>
      <SettingsCard
        id="account"
        title="Your account"
        description="Team owners add people by user ID — share yours if you need access to another workspace."
      >
        {user && (
          <DescriptionList
            columns={2}
            items={[
              {
                label: 'User ID',
                value: (
                  <span className="inline-flex items-center gap-1 font-mono text-[13px]">
                    {user.id}
                    <CopyButton value={String(user.id)} label="Copy user ID" />
                  </span>
                ),
              },
              {
                label: 'Role',
                value: <span className="capitalize">{roleLabel.replace('_', ' ')}</span>,
              },
              { label: 'Username', value: user.username, mono: true },
              { label: 'Email', value: user.email },
              {
                label: 'Name',
                value: [user.first_name, user.last_name].filter(Boolean).join(' ') || null,
              },
              { label: 'Phone', value: user.phone || null, mono: true },
            ]}
          />
        )}
      </SettingsCard>
      <SettingsCard
        id="password"
        title="Password"
        description="Use at least 8 characters that are not all digits. You stay signed in here; every other device and browser is signed out."
      >
        <ChangePasswordForm />
      </SettingsCard>
    </>
  );
}

function ChangePasswordForm() {
  const toast = useToast();
  const { principal, signIn, signOut } = useAuth();
  const form = useForm<ChangePasswordInput, unknown, ChangePasswordOutput>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: { old_password: '', new_password: '', confirm: '' },
    mode: 'onTouched',
  });
  const { message, reset: resetErrors, captureError } = useFormSubmit(form.setError, FIELDS);
  const errors = form.formState.errors;
  const submit = form.handleSubmit(async (values) => {
    resetErrors();
    try {
      await accountApi.changePassword({
        old_password: values.old_password,
        new_password: values.new_password,
      });
    } catch (error) {
      captureError(error);
      return;
    }
    form.reset();
    // The API revokes every token issued before the change (SimpleJWT CHECK_REVOKE_TOKEN), so
    // re-authenticate with the new password now instead of letting the next request fail.
    try {
      if (!principal) throw new Error('no principal');
      await signIn(await authApi.login(principal.user.username, values.new_password));
      toast.success('Password changed', 'Other devices will need to sign in again.');
    } catch {
      await signOut('Your password was changed. Please sign in again.');
    }
  });
  return (
    <form
      onSubmit={(e) => void submit(e)}
      noValidate
      className="flex flex-col gap-4"
      aria-label="Change password"
    >
      {message && <Alert tone="danger">{message}</Alert>}
      <FormField label="Current password" required error={errors.old_password?.message}>
        <PasswordInput autoComplete="current-password" {...form.register('old_password')} />
      </FormField>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label="New password" required error={errors.new_password?.message}>
          <PasswordInput autoComplete="new-password" {...form.register('new_password')} />
        </FormField>
        <FormField label="Confirm new password" required error={errors.confirm?.message}>
          <PasswordInput autoComplete="new-password" {...form.register('confirm')} />
        </FormField>
      </div>
      <div className="flex justify-end border-t border-border pt-4">
        <Button type="submit" loading={form.formState.isSubmitting}>
          Change password
        </Button>
      </div>
    </form>
  );
}
