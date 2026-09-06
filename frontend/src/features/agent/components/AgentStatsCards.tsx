import { Ticket, Wallet } from 'lucide-react';
import { Stat } from '@/components/ui';
import { ErrorState } from '@/components/feedback';
import { formatKobo } from '@/lib/formatting/money';
import type { AgentStats } from '@/types/api';

export function AgentStatsCards({
  stats,
  loading,
  error,
  onRetry,
}: {
  stats: AgentStats | undefined;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
}) {
  if (error && !stats)
    return <ErrorState error={error} onRetry={onRetry} title="Could not load your numbers" />;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      <Stat
        tone="brand"
        label="Wallet balance"
        value={stats ? formatKobo(stats.wallet_balance) : '—'}
        loading={loading}
        icon={<Wallet className="size-4" aria-hidden />}
        className="col-span-2 sm:col-span-1"
      />
      <Stat
        label="Sold today"
        value={stats ? stats.vouchers_today.toLocaleString() : '—'}
        loading={loading}
        icon={<Ticket className="size-4" aria-hidden />}
      />
      <Stat
        label="Total sold"
        value={stats ? stats.total_vouchers.toLocaleString() : '—'}
        loading={loading}
      />
      {/* Gap #5: commission is never computed by the backend, so the card only appears when it carries a value. */}
      {stats && stats.commission_this_month > 0 && (
        <Stat
          label="Commission this month"
          value={formatKobo(stats.commission_this_month)}
          className="col-span-2 sm:col-span-3"
        />
      )}
    </div>
  );
}
