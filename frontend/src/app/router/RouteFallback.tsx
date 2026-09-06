import { Spinner } from '@/components/ui/Spinner';

export function RouteFallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center" aria-busy>
      <Spinner />
    </div>
  );
}
