import { Link, Outlet } from 'react-router';
import { useAuth } from '@/app/auth/useAuth';
import { homePathFor } from '@/services/auth/principal';
import { cn } from '@/lib/utilities/cn';
import { BrandMark } from './BrandMark';

/**
 * Minimal centred layout for sign-in, registration, reset, invitation and public
 * pages. `wide` gives the landing page a roomier container.
 */
export function PublicLayout({ wide = false }: { wide?: boolean }) {
  const { principal } = useAuth();
  const width = wide ? 'max-w-6xl' : 'max-w-5xl';
  return (
    <div className="flex min-h-dvh flex-col bg-canvas">
      <header
        className={cn('mx-auto flex w-full items-center justify-between px-4 py-4 sm:px-6', width)}
      >
        <Link to="/" aria-label="Home">
          <BrandMark />
        </Link>
        <nav className="flex items-center gap-4 text-sm" aria-label="Public">
          <Link to="/pricing" className="text-ink-600 hover:text-ink-900">
            Pricing
          </Link>
          {principal ? (
            <Link
              to={homePathFor(principal)}
              className="font-medium text-brand-600 hover:underline"
            >
              Go to dashboard
            </Link>
          ) : (
            <Link to="/login" className="font-medium text-brand-600 hover:underline">
              Sign in
            </Link>
          )}
        </nav>
      </header>
      <main className={cn('mx-auto flex w-full flex-1 flex-col px-4 pb-10 sm:px-6', width)}>
        <Outlet />
      </main>
      <footer className={cn('mx-auto w-full px-4 py-4 text-xs text-ink-400 sm:px-6', width)}>
        © {new Date().getFullYear()} Yarotech Network
      </footer>
    </div>
  );
}
