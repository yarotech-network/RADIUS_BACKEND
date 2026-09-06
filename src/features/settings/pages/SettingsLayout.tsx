import { NavLink, Outlet } from 'react-router';
import { PageHeader } from '@/components/layout';
import { usePrincipal } from '@/app/auth/useAuth';
import { cn } from '@/lib/utilities/cn';
import { can, canAny, type Capability } from '@/services/auth/principal';

const TABS: { to: string; label: string; caps: Capability[] }[] = [
  { to: '/settings/general', label: 'General', caps: ['settings.profile', 'team.view'] },
  { to: '/settings/billing', label: 'Billing & payouts', caps: ['settings.billing'] },
  { to: '/settings/team', label: 'Team', caps: ['team.view'] },
  { to: '/settings/subscription', label: 'Subscription', caps: ['subscription.view'] },
];

/** Shared header + tab strip for /settings/*. Each tab is also route-guarded. */
export default function SettingsLayout() {
  const principal = usePrincipal();
  const tabs = TABS.filter((t) => canAny(principal, t.caps));
  const canEditProfile = can(principal, 'settings.profile');
  return (
    <>
      <PageHeader
        title="Settings"
        description={
          canEditProfile
            ? 'Your business details, payment configuration, team and subscription.'
            : 'Your account, team and subscription.'
        }
      />
      <nav
        aria-label="Settings sections"
        className="mb-6 no-scrollbar flex gap-1 overflow-x-auto border-b border-border"
      >
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              cn(
                '-mb-px border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors',
                isActive
                  ? 'border-brand-600 text-brand-700'
                  : 'border-transparent text-ink-500 hover:border-border hover:text-ink-900',
              )
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </>
  );
}
