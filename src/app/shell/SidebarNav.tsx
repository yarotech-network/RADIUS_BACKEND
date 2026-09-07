import { NavLink } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import type { NavGroup } from '@/app/navigation/navConfig';
import { prefetchRoute } from '@/app/navigation/prefetch';
import { cn } from '@/lib/utilities/cn';
import { Tooltip } from '@/components/ui/Tooltip';

/**
 * Dark-blue vertical navigation. `collapsed` renders the 72px icon rail (tablet, or user toggle).
 */
export function SidebarNav({
  groups,
  collapsed,
  onNavigate,
}: {
  groups: NavGroup[];
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const queryClient = useQueryClient();
  return (
    <nav
      aria-label="Primary"
      className="flex flex-1 scrollbar-thin flex-col gap-4 overflow-y-auto px-2 py-3"
    >
      {groups.map((group) => (
        <div key={group.key}>
          {group.label && !collapsed && (
            <p className="px-3 pb-1 text-[11px] font-semibold tracking-wider text-brand-300/80 uppercase">
              {group.label}
            </p>
          )}
          {group.label && collapsed && <div className="mx-3 my-2 h-px bg-white/10" aria-hidden />}
          <ul className="space-y-0.5">
            {group.items.map((item) => {
              const link = (
                <NavLink
                  to={item.to}
                  end={item.end ?? false}
                  onClick={onNavigate}
                  onMouseEnter={() => prefetchRoute(item.to, queryClient)}
                  onFocus={() => prefetchRoute(item.to, queryClient)}
                  className={({ isActive }) =>
                    cn(
                      'group flex h-10 items-center gap-3 rounded-control px-3 text-sm font-medium transition-colors',
                      'focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-white/70',
                      isActive
                        ? 'bg-white/12 text-white'
                        : 'text-brand-100/85 hover:bg-white/8 hover:text-white',
                      collapsed && 'justify-center px-0',
                    )
                  }
                >
                  <item.icon className="size-[18px] shrink-0" aria-hidden />
                  {!collapsed && <span className="truncate">{item.label}</span>}
                  {collapsed && <span className="sr-only">{item.label}</span>}
                </NavLink>
              );
              return (
                <li key={item.key}>
                  {collapsed ? (
                    <Tooltip
                      content={item.label}
                      side="bottom"
                      className="w-full [&>span[role=tooltip]]:top-1/2 [&>span[role=tooltip]]:left-[calc(100%+0.5rem)] [&>span[role=tooltip]]:mt-0 [&>span[role=tooltip]]:translate-x-0 [&>span[role=tooltip]]:-translate-y-1/2"
                    >
                      {link}
                    </Tooltip>
                  ) : (
                    link
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
