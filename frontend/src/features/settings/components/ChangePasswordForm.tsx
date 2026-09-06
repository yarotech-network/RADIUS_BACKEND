import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button, FormField, PasswordInput } from '@/components/ui';
import { Alert, useToast } from '@/components/feedback';
import { useAuth } from '@/app/auth/useAuth';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { accountApi, authApi } from '@/features/auth/api';
import {
  changePasswordSchema,
  type ChangePasswordInput,
  type ChangePasswordOutput,
} from '../settingsSchemas';

const FIELDS = ['old_password', 'new_password', 'confirm'] as const;

/**
 * Shared by workspace settings and the agent profile. The API revokes every token issued before
 * the change (SimpleJWT CHECK_REVOKE_TOKEN), so we re-authenticate with the new password right
 * away — through `agent/login/` for agents, whose accounts `auth/login/` also accepts but whose
 * portal session should come from the agent endpoint.
 */
export function ChangePasswordForm({ loginKind = 'user' }: { loginKind?: 'user' | 'agent' }) {
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
    try {
      if (!principal) throw new Error('no principal');
      const username = principal.user.username;
      const tokens =
        loginKind === 'agent'
          ? await authApi.agentLogin(username, values.new_password)
          : await authApi.login(username, values.new_password);
      await signIn(tokens);
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
