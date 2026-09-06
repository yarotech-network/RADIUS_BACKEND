import { useEffect } from 'react';
import { Link } from 'react-router';
import { ArrowRight, ShoppingBag, Ticket, Wallet } from 'lucide-react';
import { usePrincipal } from '@/app/auth/useAuth';
import { Section, StatusBadge } from '@/components/layout';
import { ButtonLink, Skeleton } from '@/components/ui';
import { formatKobo } from '@/lib/formatting/money';
import { formatRelative } from '@/lib/formatting/dates';
import { useAgentMe, useAgentStats, useAllocationHistory } from '../queries';
import { useStoreSlug } from '../storeSlug';
import { AgentStatsCards } from '../components/AgentStatsCards';
import { StoreLinkForm } from '../components/StoreLink';

export default function AgentHomePage() {
  const principal = usePrincipal();
  const me = useAgentMe();
  const stats = useAgentStats();
  const recent = useAllocationHistory({ page_size: 5 });
  const [slug] = useStoreSlug();

  useEffect(() => {
    document.title = 'Home · Agent portal';
  }, []);

  const firstName = principal?.user.first_name || principal?.user.username || '';

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm text-ink-500">{greeting()},</p>
        <h1 className="text-2xl font-semibold text-brand-950">{firstName}</h1>
        {me.data?.shop_name && <p className="text-sm text-ink-500">{me.data.shop_name}</p>}
      </header>

      <AgentStatsCards
        stats={stats.data}
        loading={stats.isPending}
        error={stats.error}
        onRetry={() => void stats.refetch()}
      />

      <div className="grid grid-cols-2 gap-3">
        <ButtonLink
          to="/agent/sell"
          size="lg"
          block
          leadingIcon={<ShoppingBag className="size-4" aria-hidden />}
        >
          Sell voucher
        </ButtonLink>
        <ButtonLink
          to="/agent/wallet?fund=1"
          size="lg"
          block
          variant="secondary"
          leadingIcon={<Wallet className="size-4" aria-hidden />}
        >
          Fund wallet
        </ButtonLink>
      </div>

      {!slug && <StoreLinkForm />}

      <Section
        title="Recent sales"
        actions={
          <Link
            to="/agent/vouchers"
            className="inline-flex items-center gap-1 text-sm font-medium text-brand-600 hover:underline"
          >
            All vouchers <ArrowRight className="size-4" aria-hidden />
          </Link>
        }
      >
        {recent.isPending ? (
          <div className="space-y-2" aria-busy>
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : recent.isError ? (
          <p className="text-sm text-ink-500">Could not load recent sales.</p>
        ) : recent.data.results.length === 0 ? (
          <div className="rounded-card border border-dashed border-border p-6 text-center">
            <Ticket className="mx-auto size-6 text-ink-400" aria-hidden />
            <p className="mt-2 text-sm font-medium text-ink-900">No vouchers sold yet</p>
            <p className="mt-1 text-sm text-ink-500">Your first sale will show up here.</p>
          </div>
        ) : (
          <ul className="divide-y divide-border rounded-card border border-border bg-surface">
            {recent.data.results.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <code className="font-mono text-sm font-semibold text-ink-900">
                    {a.voucher_username}
                  </code>
                  <div className="text-xs text-ink-500">{formatRelative(a.created_at)}</div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-ink-700 tabular-nums">
                    {formatKobo(a.amount_charged)}
                  </span>
                  <StatusBadge status={a.allocation_type} size="sm" dot={false} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}
