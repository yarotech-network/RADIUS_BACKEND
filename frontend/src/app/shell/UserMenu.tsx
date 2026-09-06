import { ChevronDown, LogOut, UserCircle } from 'lucide-react';
import { useNavigate } from 'react-router';
import { useAuth } from '@/app/auth/useAuth';
import { Menu } from '@/components/ui/Menu';
import { Avatar } from '@/components/ui/Avatar';
import { displayName, initials } from '@/services/auth/principal';
import { cn } from '@/lib/utilities/cn';

export function UserMenu({
  profilePath,
  compact = false,
  className,
}: {
  profilePath: string | null;
  compact?: boolean;
  className?: string;
}) {
  const { principal, signOut } = useAuth();
  const navigate = useNavigate();
  if (!principal) return null;
  const { user } = principal;
  return (
    <Menu
      className={className}
      items={[
        {
          key: 'profile',
          label: 'Profile',
          icon: <UserCircle />,
          onSelect: () => profilePath && navigate(profilePath),
          hidden: !profilePath,
        },
        'separator',
        {
          key: 'signout',
          label: 'Sign out',
          icon: <LogOut />,
          tone: 'danger',
          onSelect: () => void signOut(),
        },
      ]}
      trigger={({ ref, ...props }) => (
        <button
          ref={ref}
          type="button"
          aria-label="Account menu"
          className={cn(
            'flex h-10 items-center gap-2 rounded-control pr-2 pl-1 text-left transition-colors hover:bg-slate-100 focus-visible:outline-brand-600',
            compact && 'pr-1',
          )}
          {...props}
        >
          <Avatar initials={initials(user)} size="sm" />
          {!compact && (
            <span className="hidden min-w-0 flex-col leading-tight sm:flex">
              <span className="max-w-36 truncate text-sm font-medium text-ink-900">
                {displayName(user)}
              </span>
              <span className="max-w-36 truncate text-[11px] text-ink-500">
                {principal.kind === 'member' ? principal.tenantName : user.role.replace('_', ' ')}
              </span>
            </span>
          )}
          <ChevronDown className="hidden size-4 text-ink-400 sm:block" aria-hidden />
        </button>
      )}
    />
  );
}
