import { WORKSPACE_NAV } from '@/app/navigation/navConfig';
import { useAuth } from '@/app/auth/useAuth';
import { AppShell } from './AppShell';
import { TenantSwitcher } from './TenantSwitcher';

export function WorkspaceLayout() {
  const { principal } = useAuth();
  const isStaff = principal?.kind === 'platform_staff';
  const tenantName = principal?.kind === 'member' ? principal.tenantName : null;
  return (
    <AppShell
      groups={WORKSPACE_NAV}
      homePath="/"
      profilePath="/settings/profile"
      topBarStart={
        isStaff ? (
          <TenantSwitcher />
        ) : tenantName ? (
          <span className="truncate text-sm font-medium text-ink-700">{tenantName}</span>
        ) : null
      }
      sidebarBadge={
        isStaff ? (
          <span className="inline-flex rounded-full bg-white/10 px-2 py-0.5 text-[11px] font-medium text-brand-100">
            Platform staff
          </span>
        ) : null
      }
    />
  );
}
