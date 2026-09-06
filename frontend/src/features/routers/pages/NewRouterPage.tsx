import { useState } from 'react';
import { useNavigate } from 'react-router';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { PageHeader } from '@/components/layout';
import { Button, Card, FormField, PasswordInput } from '@/components/ui';
import { Alert, useToast } from '@/components/feedback';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import { cn } from '@/lib/utilities/cn';
import { useCreateRouter } from '../queries';
import {
  CREATE_DEFAULTS,
  createFormToPayload,
  routerCreateSchema,
  type RouterCreateInput,
  type RouterCreateOutput,
} from '../routerSchemas';
import {
  RouterBasicsFields,
  RouterOsUsernameField,
  RouterWireGuardFields,
} from '../components/RouterFields';

const FIELDS = [
  'name',
  'ip_address',
  'location',
  'wireguard_ip',
  'wireguard_public_key',
  'wireguard_port',
  'routeros_username',
  'is_active',
  'nas_secret',
  'routeros_password',
] as const;
const ALIASES = { routeros_password_encrypted: 'routeros_password' };

const STEPS = [
  {
    key: 'basics',
    title: 'Basics',
    fields: ['name', 'ip_address', 'location', 'is_active'] as const,
  },
  { key: 'radius', title: 'RADIUS secret', fields: ['nas_secret'] as const },
  {
    key: 'vpn',
    title: 'WireGuard',
    fields: ['wireguard_ip', 'wireguard_public_key', 'wireguard_port'] as const,
    optional: true,
  },
  {
    key: 'routeros',
    title: 'RouterOS access',
    fields: ['routeros_username', 'routeros_password'] as const,
    optional: true,
  },
] as const;

export default function NewRouterPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const create = useCreateRouter();
  const [idempotencyKey] = useState(() => newIdempotencyKey('router'));
  const [step, setStep] = useState(0);
  const form = useForm<RouterCreateInput, unknown, RouterCreateOutput>({
    resolver: zodResolver(routerCreateSchema),
    defaultValues: CREATE_DEFAULTS,
    mode: 'onTouched',
  });
  const {
    message,
    reset: resetErrors,
    captureError,
  } = useFormSubmit(form.setError, FIELDS, ALIASES);
  const current = STEPS[step]!;
  const last = step === STEPS.length - 1;

  async function next() {
    const valid = await form.trigger([...current.fields]);
    if (valid) setStep((s) => Math.min(s + 1, STEPS.length - 1));
  }

  const submit = form.handleSubmit(
    async (values) => {
      resetErrors();
      try {
        const router = await create.mutateAsync({
          payload: createFormToPayload(values),
          idempotencyKey,
        });
        toast.success('Router registered', `${router.name} is pending review.`);
        navigate(`/routers/${router.id}`, { replace: true });
      } catch (error) {
        captureError(error);
        // Jump to the first step that has an error so the user sees it.
        const errored = Object.keys(form.formState.errors);
        const idx = STEPS.findIndex((s) => s.fields.some((f) => errored.includes(f)));
        if (idx >= 0) setStep(idx);
      }
    },
    (errors) => {
      const idx = STEPS.findIndex((s) => s.fields.some((f) => f in errors));
      if (idx >= 0) setStep(idx);
    },
  );

  const errors = form.formState.errors;

  return (
    <>
      <PageHeader
        title="Add router"
        description="Register a MikroTik as a RADIUS client. You can fill in VPN and RouterOS details later."
        backTo="/routers"
        crumbs={[{ label: 'Routers', to: '/routers' }, { label: 'Add router' }]}
      />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (last) void submit(e);
          else void next();
        }}
        noValidate
        className="grid gap-6 lg:grid-cols-[14rem_1fr]"
      >
        <ol className="flex gap-2 overflow-x-auto lg:flex-col" aria-label="Steps">
          {STEPS.map((s, i) => {
            const state = i === step ? 'current' : i < step ? 'done' : 'todo';
            return (
              <li key={s.key} className="shrink-0">
                <button
                  type="button"
                  onClick={() => i < step && setStep(i)}
                  disabled={i > step}
                  aria-current={state === 'current' ? 'step' : undefined}
                  className={cn(
                    'flex w-full items-center gap-3 rounded-control px-3 py-2 text-left text-sm transition-colors disabled:cursor-not-allowed',
                    state === 'current'
                      ? 'bg-brand-50 text-brand-800'
                      : 'text-ink-600 hover:bg-surface-muted disabled:hover:bg-transparent',
                  )}
                >
                  <span
                    className={cn(
                      'grid h-6 w-6 shrink-0 place-items-center rounded-full border text-xs font-semibold',
                      state === 'done'
                        ? 'border-brand-600 bg-brand-600 text-white'
                        : state === 'current'
                          ? 'border-brand-600 text-brand-700'
                          : 'border-border-strong text-ink-400',
                    )}
                  >
                    {i + 1}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{s.title}</span>
                    {'optional' in s && s.optional && (
                      <span className="block text-xs text-ink-400">Optional</span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>

        <Card className="flex flex-col gap-5">
          {message && <Alert tone="danger">{message}</Alert>}
          <div>
            <h2 className="text-base font-semibold text-ink-900">
              Step {step + 1} of {STEPS.length}: {current.title}
            </h2>
            {current.key === 'radius' && (
              <p className="mt-1 text-sm text-ink-600">
                The shared secret configured under RADIUS on the router. It is stored encrypted and
                can only be rotated, never displayed.
              </p>
            )}
            {current.key === 'vpn' && (
              <p className="mt-1 text-sm text-ink-600">
                Needed for remote provisioning over the management VPN. Skip if the router is on a
                directly reachable network.
              </p>
            )}
            {current.key === 'routeros' && (
              <p className="mt-1 text-sm text-ink-600">
                Lets the provisioning agent push configuration to the router. Stored encrypted.
              </p>
            )}
          </div>

          {current.key === 'basics' && (
            <RouterBasicsFields register={form.register} errors={errors} control={form.control} />
          )}
          {current.key === 'radius' && (
            <FormField
              label="RADIUS shared secret"
              required
              hint="At least 8 characters. Must match the router's RADIUS client configuration."
              error={errors.nas_secret?.message}
            >
              <PasswordInput
                autoComplete="new-password"
                autoFocus
                spellCheck={false}
                className="font-mono"
                {...form.register('nas_secret')}
              />
            </FormField>
          )}
          {current.key === 'vpn' && (
            <RouterWireGuardFields register={form.register} errors={errors} />
          )}
          {current.key === 'routeros' && (
            <div className="grid gap-4 sm:grid-cols-2">
              <RouterOsUsernameField register={form.register} errors={errors} />
              <FormField
                label="RouterOS password"
                optionalLabel
                error={errors.routeros_password?.message}
              >
                <PasswordInput
                  autoComplete="new-password"
                  {...form.register('routeros_password')}
                />
              </FormField>
            </div>
          )}

          <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:justify-between">
            <Button
              type="button"
              variant="ghost"
              leadingIcon={<ChevronLeft className="h-4 w-4" aria-hidden />}
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              disabled={step === 0}
            >
              Back
            </Button>
            <div className="flex flex-col-reverse gap-2 sm:flex-row">
              <Button type="button" variant="secondary" onClick={() => navigate('/routers')}>
                Cancel
              </Button>
              {last ? (
                <Button type="submit" loading={form.formState.isSubmitting}>
                  Register router
                </Button>
              ) : (
                <Button
                  type="submit"
                  trailingIcon={<ChevronRight className="h-4 w-4" aria-hidden />}
                >
                  Continue
                </Button>
              )}
            </div>
          </div>
        </Card>
      </form>
    </>
  );
}
