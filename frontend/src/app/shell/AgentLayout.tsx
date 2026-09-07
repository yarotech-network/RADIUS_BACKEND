import { Link, NavLink, Outlet, useLocation } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { AGENT_NAV } from '@/app/navigation/navConfig';
import { prefetchRoute } from '@/app/navigation/prefetch';
import { ErrorBoundary } from '@/components/feedback/ErrorBoundary';
import { cn } from '@/lib/utilities/cn';
import { BrandMark } from './BrandMark';
import { UserMenu } from './UserMenu';

/** Mobile-first agent portal: top bar + bottom tabs; centred column on larger screens. */
export function AgentLayout() {
  const location = useLocation();
  const queryClient = useQueryClient();
  return (
    <div className="min-h-dvh bg-canvas">
      <a
        href="#main"
        className="sr-only z-50 rounded-control bg-brand-950 px-3 py-2 text-white focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-20 border-b border-border bg-surface">
        <div className="mx-auto flex h-14 max-w-3xl items-center justify-between px-4">
          <Link to="/agent" aria-label="Home">
            <BrandMark size="sm" />
          </Link>
          <nav aria-label="Primary" className="hidden items-center gap-1 sm:flex">
            {AGENT_NAV.map((item) => (
              <NavLink
                key={item.key}
                to={item.to}
                end={item.end ?? false}
                onMouseEnter={() => prefetchRoute(item.to, queryClient)}
                onFocus={() => prefetchRoute(item.to, queryClient)}
                className={({ isActive }) =>
                  cn(
                    'rounded-control px-3 py-1.5 text-sm font-medium',
                    isActive ? 'bg-brand-50 text-brand-700' : 'text-ink-600 hover:text-ink-900',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <UserMenu profilePath="/agent/profile" compact />
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-3xl px-4 pt-4 pb-24 sm:pb-10">
        <ErrorBoundary resetKey={location.pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface safe-bottom sm:hidden"
      >
        <ul className="grid grid-cols-5">
          {AGENT_NAV.map((item) => (
            <li key={item.key}>
              <NavLink
                to={item.to}
                end={item.end ?? false}
                onMouseEnter={() => prefetchRoute(item.to, queryClient)}
                onFocus={() => prefetchRoute(item.to, queryClient)}
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
        </ul>
      </nav>
    </div>
  );
}
