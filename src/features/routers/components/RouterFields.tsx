import { Controller, type Control, type FieldErrors, type UseFormRegister } from 'react-hook-form';
import { Checkbox, FormField, Input } from '@/components/ui';
import type { RouterCreateInput } from '../routerSchemas';

/**
 * Field groups shared by the register and edit forms. Typed against the create shape; the edit
 * form is a strict subset so the same components work for both.
 */
type AnyRouterForm = RouterCreateInput;

interface GroupProps {
  register: UseFormRegister<AnyRouterForm>;
  errors: FieldErrors<AnyRouterForm>;
}

export function RouterBasicsFields({
  register,
  errors,
  control,
}: GroupProps & { control: Control<AnyRouterForm> }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField
        label="Name"
        required
        hint="How this router appears in lists and sessions."
        error={errors.name?.message}
      >
        <Input autoFocus placeholder="e.g. mikrotik-wuse-01" {...register('name')} />
      </FormField>
      <FormField
        label="NAS IP address"
        required
        hint="The address FreeRADIUS sees requests from."
        error={errors.ip_address?.message}
      >
        <Input
          inputMode="decimal"
          placeholder="10.100.100.12"
          className="font-mono"
          {...register('ip_address')}
        />
      </FormField>
      <FormField
        label="Location"
        optionalLabel
        className="sm:col-span-2"
        error={errors.location?.message}
      >
        <Input placeholder="e.g. Wuse 2, Abuja" {...register('location')} />
      </FormField>
      <Controller
        control={control}
        name="is_active"
        render={({ field }) => (
          <Checkbox
            checked={field.value}
            onChange={(e) => field.onChange(e.target.checked)}
            label="Active"
            description="Inactive routers are ignored by provisioning and session views."
          />
        )}
      />
    </div>
  );
}

export function RouterWireGuardFields({ register, errors }: GroupProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField
        label="WireGuard IP"
        optionalLabel
        hint="Peer address inside the managed VPN subnet."
        error={errors.wireguard_ip?.message}
      >
        <Input
          inputMode="decimal"
          placeholder="10.100.100.12"
          className="font-mono"
          {...register('wireguard_ip')}
        />
      </FormField>
      <FormField label="Listen port" error={errors.wireguard_port?.message}>
        <Input
          type="number"
          min={1}
          max={65535}
          inputMode="numeric"
          {...register('wireguard_port')}
        />
      </FormField>
      <FormField
        label="Router public key"
        optionalLabel
        hint="44-character base64 key from the router's WireGuard interface."
        className="sm:col-span-2"
        error={errors.wireguard_public_key?.message}
      >
        <Input
          spellCheck={false}
          autoComplete="off"
          placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx="
          className="font-mono"
          {...register('wireguard_public_key')}
        />
      </FormField>
    </div>
  );
}

export function RouterOsUsernameField({ register, errors }: GroupProps) {
  return (
    <FormField
      label="RouterOS username"
      optionalLabel
      hint="Used by the provisioning agent to configure the router."
      error={errors.routeros_username?.message}
    >
      <Input autoComplete="off" placeholder="admin" {...register('routeros_username')} />
    </FormField>
  );
}
