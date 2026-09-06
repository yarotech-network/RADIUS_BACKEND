import { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button, Checkbox, Dialog, FormField, Input, Select } from '@/components/ui';
import { Alert } from '@/components/feedback';
import { useFormSubmit } from '@/lib/forms/useFormSubmit';
import { newIdempotencyKey } from '@/lib/utilities/idempotency';
import { usePlanOptions } from '@/features/plans/queries';
import type { MacDevice } from '@/types/api';
import { useCreateDevice, useUpdateDevice } from '../queries';
import {
  deviceDefaults,
  deviceSchema,
  deviceToForm,
  formToPatch,
  formToPayload,
  type DeviceInput,
  type DeviceOutput,
} from '../deviceSchemas';

const FIELDS = ['device_name', 'mac_address', 'plan', 'expires_at', 'is_active'] as const;

export function DeviceDialog({
  open,
  device,
  onClose,
  onSaved,
}: {
  open: boolean;
  device?: MacDevice;
  onClose: () => void;
  onSaved: (device: MacDevice) => void;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      variant="drawer"
      size="md"
      title={device ? `Edit ${device.device_name}` : 'Register device'}
      description={
        device
          ? 'Changes apply the next time the device authenticates.'
          : 'Devices with a registered MAC address connect without a voucher, on the plan you choose, until the expiry date.'
      }
    >
      {open && <DeviceForm {...(device ? { device } : {})} onCancel={onClose} onSaved={onSaved} />}
    </Dialog>
  );
}

function DeviceForm({
  device,
  onCancel,
  onSaved,
}: {
  device?: MacDevice;
  onCancel: () => void;
  onSaved: (device: MacDevice) => void;
}) {
  const create = useCreateDevice();
  const update = useUpdateDevice();
  const plans = usePlanOptions(true);
  const [idempotencyKey] = useState(() => newIdempotencyKey('device'));
  const form = useForm<DeviceInput, unknown, DeviceOutput>({
    resolver: zodResolver(deviceSchema),
    defaultValues: device ? deviceToForm(device) : deviceDefaults(),
    mode: 'onTouched',
  });
  const { message, reset: resetErrors, captureError } = useFormSubmit(form.setError, FIELDS);
  const errors = form.formState.errors;

  const submit = form.handleSubmit(async (values) => {
    resetErrors();
    try {
      if (device) {
        const patch = formToPatch(values, device);
        if (Object.keys(patch).length === 0) {
          onCancel();
          return;
        }
        onSaved(await update.mutateAsync({ id: device.id, payload: patch }));
      } else {
        onSaved(await create.mutateAsync({ payload: formToPayload(values), idempotencyKey }));
      }
    } catch (error) {
      captureError(error);
    }
  });

  const planOptions = [
    { value: '', label: plans.isPending ? 'Loading plans…' : 'Choose a plan' },
    ...(plans.data ?? []).map((p) => ({
      value: String(p.id),
      label: `${p.name} · ${p.price_display}`,
    })),
  ];
  // Keep the current plan selectable even if it has since been deactivated.
  if (device && plans.data && !plans.data.some((p) => p.id === device.plan))
    planOptions.push({ value: String(device.plan), label: `${device.plan_name} (inactive)` });

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-4">
      {message && <Alert tone="danger">{message}</Alert>}
      {plans.isError && (
        <Alert tone="warning">
          Plans could not be loaded — you can still fill in the other fields.
        </Alert>
      )}
      <FormField label="Device name" required error={errors.device_name?.message}>
        <Input autoFocus placeholder="e.g. Lobby smart TV" {...form.register('device_name')} />
      </FormField>
      <FormField
        label="MAC address"
        required
        hint="Any common format; it is stored as AA:BB:CC:DD:EE:FF."
        error={errors.mac_address?.message}
      >
        <Input
          autoComplete="off"
          spellCheck={false}
          placeholder="AA:BB:CC:DD:EE:FF"
          className="font-mono uppercase"
          {...form.register('mac_address')}
        />
      </FormField>
      <FormField
        label="Plan"
        required
        hint="Speed and data limits applied to the device."
        error={errors.plan?.message}
      >
        <Select options={planOptions} disabled={plans.isPending} {...form.register('plan')} />
      </FormField>
      <FormField
        label="Access expires"
        required
        hint="After this the device must be renewed here."
        error={errors.expires_at?.message}
      >
        <Input type="datetime-local" {...form.register('expires_at')} />
      </FormField>
      <Controller
        control={form.control}
        name="is_active"
        render={({ field }) => (
          <Checkbox
            checked={field.value}
            onChange={(e) => field.onChange(e.target.checked)}
            label="Active"
            description="Inactive devices are refused even before they expire."
          />
        )}
      />
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
          {device ? 'Save changes' : 'Register device'}
        </Button>
      </div>
    </form>
  );
}
