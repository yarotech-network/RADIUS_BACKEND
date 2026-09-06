import { Outlet, useLocation } from 'react-router';
import { ErrorBoundary } from '@/components/feedback/ErrorBoundary';

export function RootLayout() {
  const location = useLocation();
  return (
    <ErrorBoundary resetKey={location.pathname}>
      <Outlet />
    </ErrorBoundary>
  );
}
