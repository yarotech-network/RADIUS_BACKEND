import { Building2, ChevronDown } from 'lucide-react';
import { useAuth } from '@/app/auth/useAuth';
import { Menu } from '@/components/ui/Menu';
import { cn } from '@/lib/utilities/cn';
import { tenantLabel, useAssignedTenantNames } from './useAssignedTenantNames';

export function TenantSwitcher({ className }: { className?: string }) {
  const { principal, selectTenant } = useAuth();
  const ids =
    principal?.kind === 'platform_staff' ? principal.assignments.map((a) => a.tenant) : [];
  const names = useAssignedTenantNames(ids);
  if (!principal || principal.kind !== 'platform_staff') return null;
  const active = principal.activeTenantId;
  return (
    <Menu
      className={className}
      align="start"
      items={principal.assignments.map((a) => ({
        key: String(a.tenant),
        label: (
          <span className="flex items-center gap-2">
            <span
              className={cn(
                'size-1.5 rounded-full',
                a.tenant === active ? 'bg-brand-600' : 'bg-transparent',
              )}
              aria-hidden
            />
            {tenantLabel(names.data, a.tenant)}
          </span>
        ),
        onSelect: () => selectTenant(a.tenant),
      }))}
      trigger={({ ref, ...props }) => (
        <button
          ref={ref}
          type="button"
          className="flex h-9 max-w-56 items-center gap-2 rounded-control border border-border bg-surface px-2.5 text-sm font-medium hover:bg-surface-muted focus-visible:outline-brand-600"
          {...props}
        >
          <Building2 className="size-4 shrink-0 text-ink-500" aria-hidden />
          <span className="truncate">
            {active ? tenantLabel(names.data, active) : 'Choose tenant'}
          </span>
          <ChevronDown className="size-4 shrink-0 text-ink-400" aria-hidden />
        </button>
      )}
    />
  );
}
