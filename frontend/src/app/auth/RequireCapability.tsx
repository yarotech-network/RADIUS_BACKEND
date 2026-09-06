import { Navigate, Outlet } from 'react-router';
import { can, type Capability } from '@/services/auth/principal';
import { usePrincipal } from './useAuth';

/**
 * UX-level gate for workspace pages: users without the capability are sent to the dashboard
 * (they would only receive 403s from the API anyway). Authorisation is enforced by the backend.
 */
export function RequireCapability({ capability }: { capability: Capability }) {
  const principal = usePrincipal();
  if (!can(principal, capability)) return <Navigate to="/" replace />;
  return <Outlet />;
}
