import { lazy } from 'react';
import { createBrowserRouter, Navigate, type RouteObject } from 'react-router';
import { lazyRoute } from './lazy';
import { RootLayout } from '@/app/RootLayout';

/*
 * Phase 2 route tree: only the dev gallery and a placeholder home.
 * Phase 3 adds the public/auth routes and the three surface shells.
 */
const devRoutes: RouteObject[] = import.meta.env.DEV
  ? [
      {
        path: '/__dev/ui',
        Component: lazyRoute(lazy(() => import('@/features/dev/UiGalleryPage'))),
      },
    ]
  : [];

export const router = createBrowserRouter([
  {
    Component: RootLayout,
    children: [
      {
        index: true,
        element: <Navigate to={import.meta.env.DEV ? '/__dev/ui' : '/login'} replace />,
      },
      ...devRoutes,
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);
