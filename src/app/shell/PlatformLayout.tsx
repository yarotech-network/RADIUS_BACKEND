import { PLATFORM_NAV } from '@/app/navigation/navConfig';
import { AppShell } from './AppShell';

export function PlatformLayout() {
  return (
    <AppShell
      groups={PLATFORM_NAV}
      homePath="/platform"
      profilePath={null}
      accent="platform"
      topBarStart={
        <span className="hidden text-sm font-medium text-brand-100 sm:inline">
          Platform console
        </span>
      }
      sidebarBadge={
        <span className="inline-flex rounded-full bg-brand-400/20 px-2 py-0.5 text-[11px] font-medium text-brand-100">
          Administrator
        </span>
      }
    />
  );
}
