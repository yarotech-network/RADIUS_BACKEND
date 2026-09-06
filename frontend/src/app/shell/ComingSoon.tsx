import { Construction } from 'lucide-react';
import { PageHeader } from '@/components/layout/PageHeader';
import { EmptyState } from '@/components/feedback/EmptyState';
import { Card } from '@/components/ui/Card';

/** Temporary placeholder for routes scheduled in later phases. Replaced feature by feature. */
export function ComingSoon({ title, phase }: { title: string; phase: number }) {
  return (
    <>
      <PageHeader title={title} />
      <Card padded={false}>
        <EmptyState
          icon={<Construction />}
          title={`${title} arrives in phase ${phase}`}
          description="This screen is scheduled in the implementation plan and is not available yet."
        />
      </Card>
    </>
  );
}
