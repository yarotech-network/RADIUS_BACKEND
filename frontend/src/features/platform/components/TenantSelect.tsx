import { Select } from '@/components/ui';
import { useTenantIndex } from '../queries';

/**
 * Tenant filter/picker fed by the cached tenant index. Falls back to a disabled select while
 * loading so list pages never block on it.
 */
export function TenantSelect({
  value,
  onChange,
  label = 'Tenant',
  allLabel = 'All tenants',
  includePlatform = false,
  required = false,
  size = 'sm',
  className,
  id,
  invalid,
}: {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  allLabel?: string;
  includePlatform?: boolean;
  required?: boolean;
  size?: 'sm' | 'md';
  className?: string;
  id?: string;
  invalid?: boolean;
}) {
  const index = useTenantIndex();
  const tenants = (index.data ?? []).filter((t) => includePlatform || !t.is_platform_admin);
  const options = [
    {
      value: '',
      label: index.isPending ? 'Loading tenants…' : required ? 'Choose a tenant' : allLabel,
    },
    ...tenants.map((t) => ({
      value: String(t.id),
      label: t.is_active ? t.name : `${t.name} (inactive)`,
    })),
  ];
  // Keep an unknown value (e.g. a deleted tenant id in the URL) visible instead of silently resetting.
  if (value && !tenants.some((t) => String(t.id) === value))
    options.push({ value, label: `Tenant #${value}` });
  return (
    <Select
      {...(id ? { id } : {})}
      aria-label={label}
      size={size}
      value={value}
      disabled={index.isPending}
      onChange={(e) => onChange(e.target.value)}
      options={options}
      {...(className ? { className } : {})}
      {...(invalid ? { invalid: true } : {})}
    />
  );
}
