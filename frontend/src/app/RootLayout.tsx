import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router';
import { ErrorBoundary } from '@/components/feedback/ErrorBoundary';
import { titleForPathname } from './documentTitle';

export function RootLayout() {
  const location = useLocation();
  useEffect(() => {
    const title = titleForPathname(location.pathname);
    if (title) document.title = title;
  }, [location.pathname]);
  return (
    <ErrorBoundary resetKey={location.pathname}>
      <Outlet />
    </ErrorBoundary>
  );
}
