import { Suspense, type ComponentType, type LazyExoticComponent, type ReactNode } from 'react';
import { RouteFallback } from './RouteFallback';

/** Wrap a lazily imported route component with a consistent Suspense fallback. */
export function lazyRoute<P extends object>(
  Component: LazyExoticComponent<ComponentType<P>>,
  fallback: ReactNode = <RouteFallback />,
) {
  return function LazyRoute(props: P) {
    return (
      <Suspense fallback={fallback}>
        <Component {...props} />
      </Suspense>
    );
  };
}
