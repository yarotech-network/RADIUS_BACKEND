import type { ReactNode } from 'react';
import type { UseQueryResult } from '@tanstack/react-query';
import { ErrorState } from './ErrorState';

/**
 * Renders skeleton / error / content for a single query. Keeps previously loaded data visible during
 * background refetches (only the very first load shows the skeleton).
 */
export function QueryBoundary<T>({
  query,
  skeleton,
  children,
  errorTitle,
  compact,
}: {
  query: Pick<UseQueryResult<T>, 'data' | 'error' | 'isPending' | 'isError' | 'refetch'>;
  skeleton: ReactNode;
  children: (data: T) => ReactNode;
  errorTitle?: string;
  compact?: boolean;
}) {
  if (query.isPending) return <>{skeleton}</>;
  if (query.isError && query.data === undefined) {
    return (
      <ErrorState
        error={query.error}
        onRetry={() => void query.refetch()}
        {...(errorTitle ? { title: errorTitle } : {})}
        {...(compact ? { compact } : {})}
      />
    );
  }
  return <>{children(query.data as T)}</>;
}
