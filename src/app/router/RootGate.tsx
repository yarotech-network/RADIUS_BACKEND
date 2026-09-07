import { lazy } from 'react';
import { Navigate } from 'react-router';
import { useAuth } from '@/app/auth/useAuth';
import { AppSplash } from '@/app/shell/AppSplash';
import { lazyRoute } from './lazy';

// Lazy so the landing page (and its storefront plan cards) stay out of the
// entry chunk — only visitors who actually hit `/` download it.
const LandingPage = lazyRoute(
  lazy(() => import('@/features/storefront/pages/LandingPage')),
  <AppSplash />,
);

/**
 * `/` — public landing page for visitors; signed-in users are sent straight to
 * their workspace overview at `/dashboard`. Keeping the decision in one place
 * means old bookmarks keep working for everyone.
 */
export function RootGate() {
  const { status, principal } = useAuth();
  if (status === 'booting') return <AppSplash />;
  if (principal) return <Navigate to="/dashboard" replace />;
  return <LandingPage />;
}
