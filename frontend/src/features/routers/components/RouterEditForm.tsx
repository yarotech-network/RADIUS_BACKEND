import { useForm, type UseFormRegister, type FieldErrors, type Control } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from '@/components/ui';
import { Alert } from '@/components/feedback';
import { Section } from '@/components/layout';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import type { NasDevice } from '@/types/api';
import { useUpdateRouter } from '../queries';
import {
  editFormToPatch,
  routerEditSchema,
  routerToEditForm,
  type RouterCreateInput,
  type RouterEditInput,
  type RouterEditOutput,
} from '../routerSchemas';
import { RouterBasicsFields, RouterOsUsernameField, RouterWireGuardFields } from './RouterFields';

const FIELDS = [
  'name',
  'ip_address',
  'location',
  'wireguard_ip',
  'wireguard_public_key',
  'wireguard_port',
  'routeros_username',
  'is_active',
] as const;

export function RouterEditForm({
  router,
  onSaved,
  onCancel,
}: {
  router: NasDevice;
  onSaved: (router: NasDevice) => void;
  onCancel: () => void;
}) {
  const update = useUpdateRouter();
  const form = useForm<RouterEditInput, unknown, RouterEditOutput>({
    resolver: zodResolver(routerEditSchema),
    defaultValues: routerToEditForm(router),
    mode: 'onTouched',
  });
  const { message, reset: resetErrors, captureError } = useFormSubmit(form.setError, FIELDS);

  const submit = form.handleSubmit(async (values) => {
    resetErrors();
    const patch = editFormToPatch(values, router);
    if (Object.keys(patch).length === 0) {
      onCancel();
      return;
    }
    try {
      onSaved(await update.mutateAsync({ id: router.id, payload: patch }));
    } catch (error) {
      captureError(error);
    }
  });

  // The edit form is a subset of the create form; the field groups are typed against the superset.
  const register = form.register as unknown as UseFormRegister<RouterCreateInput>;
  const errors = form.formState.errors as FieldErrors<RouterCreateInput>;
  const control = form.control as unknown as Control<RouterCreateInput>;

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-6">
      {message && <Alert tone="danger">{message}</Alert>}
      <Section title="Basics">
        <RouterBasicsFields register={register} errors={errors} control={control} />
      </Section>
      <Section
        title="WireGuard"
        description="Changing the peer settings does not re-provision automatically — run Provision again afterwards."
      >
        <RouterWireGuardFields register={register} errors={errors} />
      </Section>
      <Section
        title="RouterOS access"
        description="The RouterOS password and the RADIUS secret are changed under Secrets."
      >
        <RouterOsUsernameField register={register} errors={errors} />
      </Section>
      <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:justify-end">
        <Button
          type="button"
          variant="secondary"
          onClick={onCancel}
          disabled={form.formState.isSubmitting}
        >
          Cancel
        </Button>
        <Button type="submit" loading={form.formState.isSubmitting}>
          Save changes
        </Button>
      </div>
    </form>
  );
}
