import { Link } from 'react-router';
import { SearchX } from 'lucide-react';
import { EmptyState } from '@/components/feedback/EmptyState';

export function NotFoundPage({
  homePath = '/',
  title = 'Page not found',
  description = 'The page you are looking for does not exist or has moved.',
}: {
  homePath?: string;
  title?: string;
  description?: string;
}) {
  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <EmptyState
        icon={<SearchX />}
        title={title}
        description={description}
        action={
          <Link
            to={homePath}
            className="inline-flex h-8 items-center rounded-control border border-border bg-surface px-3 text-xs font-medium hover:bg-surface-muted"
          >
            Go home
          </Link>
        }
      />
    </div>
  );
}
