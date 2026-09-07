import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link, useNavigate } from 'react-router';
import { AuthSplitLayout } from '@/app/shell/AuthSplitLayout';
import { Alert } from '@/components/feedback/Alert';
import { Button, FormField, Input } from '@/components/ui';
import { authApi } from '@/features/auth/api';
import { PasswordInput } from '@/features/auth/components/PasswordInput';
import { useSubmitError } from '@/features/auth/useSubmitError';
import { applyApiErrors } from '@/lib/validation/applyApiErrors';
import {
  emailSchema,
  passwordPairRefinement,
  passwordPairShape,
  phoneSchema,
  usernameSchema,
} from '@/lib/validation/schemas';
import { LIMITS } from '@/app/config/constants';

const schema = z
  .object({
    tenant_name: z
      .string()
      .trim()
      .min(LIMITS.tenantNameMin, 'Enter your business name')
      .max(LIMITS.tenantNameMax),
    username: usernameSchema,
    email: emailSchema,
    phone: phoneSchema,
    ...passwordPairShape,
  })
  .refine(passwordPairRefinement.check, passwordPairRefinement.options);
type FormValues = z.infer<typeof schema>;
const FIELDS = [
  'tenant_name',
  'username',
  'email',
  'phone',
  'password',
  'password_confirm',
] as const;

export default function RegisterPage() {
  const navigate = useNavigate();
  const submitError = useSubmitError();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      tenant_name: '',
      username: '',
      email: '',
      phone: '',
      password: '',
      password_confirm: '',
    },
  });

  useEffect(() => {
    document.title = 'Create workspace · Yarotech RADIUS';
  }, []);

  const onSubmit = form.handleSubmit(async (values) => {
    submitError.reset();
    try {
      // The account is created unverified — a 6-digit OTP goes to the given
      // address and tokens are only issued once it is confirmed.
      await authApi.register(values);
      navigate('/verify-email', { state: { email: values.email } });
    } catch (error) {
      const leftover = applyApiErrors(error, form.setError, FIELDS);
      if (leftover) submitError.setMessage(leftover);
    }
  });

  const errors = form.formState.errors;

  return (
    <AuthSplitLayout
      title="Create your workspace"
      description="Sets up your business, the owner account, and a ready-to-use hotspot workspace."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-brand-600 hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        {submitError.message && <Alert tone="danger">{submitError.message}</Alert>}
        <FormField
          label="Business name"
          error={errors.tenant_name?.message}
          hint="Shown to customers on your storefront and vouchers."
          required
        >
          <Input autoComplete="organization" autoFocus {...form.register('tenant_name')} />
        </FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Username" error={errors.username?.message} required>
            <Input
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              {...form.register('username')}
            />
          </FormField>
          <FormField label="Phone" error={errors.phone?.message} required>
            <Input
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              placeholder="+234…"
              {...form.register('phone')}
            />
          </FormField>
        </div>
        <FormField label="Email" error={errors.email?.message} required>
          <Input type="email" inputMode="email" autoComplete="email" {...form.register('email')} />
        </FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="Password"
            error={errors.password?.message}
            hint="At least 8 characters, not only numbers."
            required
          >
            <PasswordInput autoComplete="new-password" {...form.register('password')} />
          </FormField>
          <FormField label="Confirm password" error={errors.password_confirm?.message} required>
            <PasswordInput autoComplete="new-password" {...form.register('password_confirm')} />
          </FormField>
        </div>
        <Button type="submit" block size="lg" loading={form.formState.isSubmitting}>
          Create workspace
        </Button>
      </form>
    </AuthSplitLayout>
  );
}
