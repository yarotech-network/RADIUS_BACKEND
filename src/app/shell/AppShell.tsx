import { useEffect, useState, type ReactNode } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router';
import { MoreHorizontal, PanelLeftClose, PanelLeftOpen, X } from 'lucide-react';
import { STORAGE_KEYS } from '@/app/config/constants';
import type { NavGroup } from '@/app/navigation/navConfig';
import { mobilePrimaryItems, visibleGroups } from '@/app/navigation/navConfig';
import { useAuth } from '@/app/auth/useAuth';
import { ErrorBoundary } from '@/components/feedback/ErrorBoundary';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utilities/cn';
import { BrandMark } from './BrandMark';
import { SidebarNav } from './SidebarNav';
import { UserMenu } from './UserMenu';

export interface AppShellProps {
  groups: NavGroup[];
  homePath: string;
  profilePath: string | null;
  /** Slot in the top bar (e.g. tenant switcher for platform staff). */
  topBarStart?: ReactNode;
  /** Extra items shown under the workspace name in the sidebar. */
  sidebarBadge?: ReactNode;
  /** Platform console uses a dark-blue top bar accent. */
  accent?: 'default' | 'platform';
}

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEYS.sidebarCollapsed) === '1';
  } catch {
    return false;
  }
}

/**
 * Responsive shell:
 *  - ≥ lg: 256px sidebar (collapsible to a 72px rail, persisted) + top bar
 *  - md–lg: rail + top bar
 *  - < md: top bar + bottom nav (4 primary items + "More" opening a drawer with everything)
 */
export function AppShell({
  groups,
  homePath,
  profilePath,
  topBarStart,
  sidebarBadge,
  accent = 'default',
}: AppShellProps) {
  const { principal } = useAuth();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [drawerState, setDrawerState] = useState<{ open: boolean; path: string }>({
    open: false,
    path: location.pathname,
  });
  // The drawer closes automatically on navigation (derived, no effect needed).
  const drawerOpen = drawerState.open && drawerState.path === location.pathname;
  const setDrawerOpen = (open: boolean) => setDrawerState({ open, path: location.pathname });
  const visible = visibleGroups(groups, principal);
  const primary = mobilePrimaryItems(groups, principal);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEYS.sidebarCollapsed, collapsed ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, [collapsed]);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDrawerState((s) => ({ ...s, open: false }));
    };
    document.addEventListener('keydown', onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previous;
    };
  }, [drawerOpen]);

  const sidebarWidth = collapsed ? 'lg:w-[72px]' : 'lg:w-64';

  return (
    <div className="min-h-dvh bg-canvas">
      <a
        href="#main"
        className="sr-only z-50 rounded-control bg-brand-950 px-3 py-2 text-white focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>

      {/* Desktop / tablet sidebar */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-30 hidden w-[72px] flex-col bg-brand-950 text-white transition-[width] duration-200 md:flex',
          sidebarWidth,
        )}
      >
        <div
          className={cn(
            'flex h-16 items-center',
            collapsed ? 'justify-center' : 'justify-center px-4 lg:justify-start',
          )}
        >
          <Link to={homePath} className="rounded focus-visible:outline-white/70" aria-label="Home">
            {/* Full wordmark only when the sidebar is expanded on desktop; the rail shows the icon. */}
            <BrandMark inverse hideText className={cn(!collapsed && 'lg:hidden')} />
            {!collapsed && <BrandMark inverse className="hidden lg:inline-flex" />}
          </Link>
        </div>
        {sidebarBadge && !collapsed && <div className="px-4 pb-2">{sidebarBadge}</div>}
        <SidebarNav groups={visible} collapsed={collapsed} />
        <div className="hidden p-2 lg:block">
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            aria-pressed={collapsed}
            className="flex h-10 w-full items-center justify-center gap-2 rounded-control text-xs font-medium text-brand-200 hover:bg-white/8 hover:text-white"
          >
            {collapsed ? (
              <PanelLeftOpen className="size-4" aria-hidden />
            ) : (
              <PanelLeftClose className="size-4" aria-hidden />
            )}
            {!collapsed && 'Collapse'}
            <span className="sr-only">
              {collapsed ? 'Expand navigation' : 'Collapse navigation'}
            </span>
          </button>
        </div>
      </aside>

      {/* Top bar */}
      <header
        className={cn(
          'sticky top-0 z-20 flex h-14 items-center gap-2 border-b px-3 sm:h-16 sm:px-5 md:pl-[calc(72px+1.25rem)]',
          collapsed ? 'lg:pl-[calc(72px+1.5rem)]' : 'lg:pl-[calc(16rem+1.5rem)]',
          accent === 'platform'
            ? 'border-brand-900 bg-brand-950 text-white'
            : 'border-border bg-surface',
        )}
      >
        <Link to={homePath} className="md:hidden" aria-label="Home">
          <BrandMark size="sm" inverse={accent === 'platform'} />
        </Link>
        <div className="flex min-w-0 flex-1 items-center gap-2 md:justify-start">{topBarStart}</div>
        <div
          className={cn(
            accent === 'platform' &&
              '[&_.text-ink-500]:text-brand-200 [&_button:hover]:bg-white/10 [&_span]:text-white',
          )}
        >
          <UserMenu profilePath={profilePath} />
        </div>
      </header>

      {/* Content */}
      <main
        id="main"
        className={cn(
          'mx-auto w-full max-w-[1440px] px-3 pt-4 pb-24 sm:px-5 sm:pt-6 md:pb-8 md:pl-[calc(72px+1.25rem)] lg:px-8',
          collapsed ? 'lg:pl-[calc(72px+2rem)]' : 'lg:pl-[calc(16rem+2rem)]',
        )}
      >
        <ErrorBoundary resetKey={location.pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>

      {/* Mobile bottom nav */}
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface safe-bottom md:hidden"
      >
        <ul className="grid auto-cols-fr grid-flow-col">
          {primary.map((item) => (
            <li key={item.key}>
              <NavLink
                to={item.to}
                end={item.end ?? false}
                className={({ isActive }) =>
                  cn(
                    'flex h-14 flex-col items-center justify-center gap-1 text-[11px] font-medium',
                    isActive ? 'text-brand-700' : 'text-ink-500',
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <span
                      className={cn(
                        'flex h-6 w-10 items-center justify-center rounded-full',
                        isActive && 'bg-brand-100',
                      )}
                    >
                      <item.icon className="size-[18px]" aria-hidden />
                    </span>
                    {item.label}
                  </>
                )}
              </NavLink>
            </li>
          ))}
          <li>
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              aria-expanded={drawerOpen}
              aria-controls="mobile-drawer"
              className="flex h-14 w-full flex-col items-center justify-center gap-1 text-[11px] font-medium text-ink-500"
            >
              <span className="flex h-6 w-10 items-center justify-center">
                <MoreHorizontal className="size-[18px]" aria-hidden />
              </span>
              More
            </button>
          </li>
        </ul>
      </nav>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 md:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation"
          id="mobile-drawer"
        >
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-brand-950/50"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 flex w-[82vw] max-w-xs flex-col bg-brand-950 text-white">
            <div className="flex h-14 items-center justify-between px-4">
              <BrandMark inverse />
              <Button
                variant="ghost"
                size="icon"
                aria-label="Close"
                onClick={() => setDrawerOpen(false)}
                className="text-white hover:bg-white/10"
              >
                <X className="size-5" />
              </Button>
            </div>
            {sidebarBadge && <div className="px-4 pb-2">{sidebarBadge}</div>}
            <SidebarNav
              groups={visible}
              collapsed={false}
              onNavigate={() => setDrawerOpen(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
