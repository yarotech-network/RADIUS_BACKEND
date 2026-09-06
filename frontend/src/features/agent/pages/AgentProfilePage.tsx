import { useEffect, type ReactNode } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { LogOut, Store } from 'lucide-react';
import { useAuth } from '@/app/auth/useAuth';
import { StatusBadge } from '@/components/layout';
import { Button, DescriptionList, FormField, Input, Skeleton } from '@/components/ui';
import { Alert, ErrorState, useToast } from '@/components/feedback';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { formatDate } from '@/lib/formatting/dates';
import { ChangePasswordForm } from '@/features/settings/components/ChangePasswordForm';
import { usePublicTenant } from '@/features/storefront/queries';
import type { AgentProfile } from '@/types/api';
import { useAgentMe, useUpdateAgentMe } from '../queries';
import { useStoreSlug } from '../storeSlug';
import { StoreLinkForm } from '../components/StoreLink';
import {
  agentProfileSchema,
  agentProfileToForm,
  agentProfileToPatch,
  type AgentProfileInput,
  type AgentProfileOutput,
} from '../profileSchema';

const FIELDS = ['shop_name', 'phone'] as const;

export default function AgentProfilePage() {
  const me = useAgentMe();
  const { principal, signOut } = useAuth();
  useEffect(() => {
    document.title = 'Profile · Agent portal';
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-brand-950">Profile</h1>
        <p className="mt-1 text-sm text-ink-500">
          Your agent account with the operator you sell for.
        </p>
      </header>

      <Card title="Account">
        {me.isPending ? (
          <Skeleton className="h-28 w-full" />
        ) : me.isError ? (
          <ErrorState
            error={me.error}
            onRetry={() => void me.refetch()}
            title="Could not load your profile"
          />
        ) : (
          <DescriptionList
            columns={2}
            items={[
              { label: 'Username', value: me.data.username, mono: true },
              { label: 'Email', value: principal?.user.email ?? null },
              { label: 'Status', value: <StatusBadge status={me.data.status} size="sm" /> },
              { label: 'Agent since', value: formatDate(me.data.created_at) },
              { label: 'Commission rate', value: `${me.data.commission_rate}%` },
              { label: 'Agent ID', value: String(me.data.id), mono: true },
            ]}
          />
        )}
      </Card>

      <Card
        title="Shop details"
        description="Shown to your operator. Your commission rate is set by them."
      >
        {me.data ? <ShopForm profile={me.data} /> : <Skeleton className="h-32 w-full" />}
      </Card>

      <StoreCard />

      <Card
        title="Password"
        description="You stay signed in here; every other device and browser is signed out."
      >
        <ChangePasswordForm loginKind="agent" />
      </Card>

      <div className="flex justify-end">
        <Button
          variant="ghost"
          onClick={() => void signOut()}
          leadingIcon={<LogOut className="size-4" aria-hidden />}
        >
          Sign out
        </Button>
      </div>
    </div>
  );
}

function Card({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section aria-label={title} className="rounded-card border border-border bg-surface p-5">
      <h2 className="text-base font-semibold text-brand-950">{title}</h2>
      {description && <p className="mt-1 mb-4 text-sm text-ink-500">{description}</p>}
      {!description && <div className="mb-4" />}
      {children}
    </section>
  );
}

function ShopForm({ profile }: { profile: AgentProfile }) {
  const toast = useToast();
  const update = useUpdateAgentMe();
  const form = useForm<AgentProfileInput, unknown, AgentProfileOutput>({
    resolver: zodResolver(agentProfileSchema),
    defaultValues: agentProfileToForm(profile),
    mode: 'onTouched',
  });
  const { message, reset: resetErrors, captureError } = useFormSubmit(form.setError, FIELDS);
  const errors = form.formState.errors;
  const submit = form.handleSubmit(async (values) => {
    resetErrors();
    const patch = agentProfileToPatch(profile, values);
    if (Object.keys(patch).length === 0) {
      toast.info('Nothing to save');
      return;
    }
    try {
      const next = await update.mutateAsync({ id: profile.id, payload: patch });
      form.reset(agentProfileToForm(next));
      toast.success('Shop details saved');
    } catch (error) {
      captureError(error);
    }
  });
  return (
    <form
      onSubmit={(e) => void submit(e)}
      noValidate
      className="flex flex-col gap-4"
      aria-label="Shop details"
    >
      {message && <Alert tone="danger">{message}</Alert>}
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label="Shop name" error={errors.shop_name?.message}>
          <Input {...form.register('shop_name')} />
        </FormField>
        <FormField label="Phone" required error={errors.phone?.message}>
          <Input type="tel" inputMode="tel" autoComplete="tel" {...form.register('phone')} />
        </FormField>
      </div>
      <div className="flex justify-end border-t border-border pt-4">
        <Button
          type="submit"
          loading={form.formState.isSubmitting}
          disabled={!form.formState.isDirty}
        >
          Save
        </Button>
      </div>
    </form>
  );
}

function StoreCard() {
  const [slug, setSlug] = useStoreSlug();
  const tenant = usePublicTenant(slug);
  return (
    <Card title="Connected storefront" description="Where your plan list and prices come from.">
      {slug ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex size-10 items-center justify-center rounded-full bg-brand-50 text-brand-700">
              <Store className="size-5" aria-hidden />
            </span>
            <div>
              <div className="text-sm font-medium text-ink-900">
                {tenant.data?.name ?? (tenant.isPending ? '…' : slug)}
              </div>
              <div className="text-xs text-ink-500">
                /s/{slug}
                {tenant.isError && ' · could not verify right now'}
              </div>
            </div>
          </div>
          <Button variant="secondary" size="sm" onClick={() => setSlug(null)}>
            Disconnect
          </Button>
        </div>
      ) : (
        <StoreLinkForm compact />
      )}
    </Card>
  );
}
