import { Spinner } from '@/components/ui/Spinner';
import { BrandMark } from './BrandMark';

export function AppSplash() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-canvas">
      <BrandMark size="lg" />
      <Spinner label="Loading your workspace" />
    </div>
  );
}
