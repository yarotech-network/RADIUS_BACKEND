import { Navigate, Outlet } from 'react-router';
import { can, canAny, type Capability } from '@/services/auth/principal';
import { usePrincipal } from './useAuth';

type Props =
  { capability: Capability; anyOf?: never } | { anyOf: Capability[]; capability?: never };

/**
 * UX-level gate for workspace pages: users without the capability are sent to the dashboard
 * (they would only receive 403s from the API anyway). Authorisation is enforced by the backend.
 */
export function RequireCapability(props: Props) {
  const principal = usePrincipal();
  const allowed = props.anyOf ? canAny(principal, props.anyOf) : can(principal, props.capability);
  if (!allowed) return <Navigate to="/" replace />;
  return <Outlet />;
}
