import { useEffect } from 'react';
import { Building2, Radio, Ticket, Users, Wallet } from 'lucide-react';
import { PageHeader, Section } from '@/components/layout';
import { ButtonLink, Stat } from '@/components/ui';
import { ErrorState } from '@/components/feedback';
import { formatKobo } from '@/lib/formatting/money';
import { formatDateTime, formatRelative } from '@/lib/formatting/dates';
import { StatusBadge } from '@/components/layout';
import { usePlatformStats, useTenants } from '../queries';

/** `/platform` — cross-tenant KPIs from `platform/dashboard/` plus the newest tenants. */
export default function PlatformOverviewPage() {
  const stats = usePlatformStats();
  const recent = useTenants({ page_size: 5, is_platform_admin: false });
  useEffect(() => {
    document.title = 'Platform overview · Yarotech RADIUS';
  }, []);

  const s = stats.data;
  const number = (n: number | undefined) => (n === undefined ? '—' : n.toLocaleString());

  return (
    <>
      <PageHeader
        title="Platform overview"
        description="Every operator on the platform at a glance. Amounts are successful payments in naira."
        meta={
          s && stats.dataUpdatedAt ? (
            <span className="text-xs text-ink-500">
              Updated {formatRelative(new Date(stats.dataUpdatedAt))}
            </span>
          ) : undefined
        }
      />
      {stats.isError && !s ? (
        <ErrorState
          error={stats.error}
          onRetry={() => void stats.refetch()}
          title="Could not load platform figures"
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat
              tone="brand"
              label="Tenants"
              value={number(s?.tenants)}
              hint={s ? `${s.active_tenants.toLocaleString()} active` : undefined}
              icon={<Building2 className="size-4" aria-hidden />}
              loading={stats.isPending}
            />
            <Stat
              label="Routers"
              value={number(s?.routers)}
              hint={s ? `${s.onboarded_routers.toLocaleString()} onboarded` : undefined}
              icon={<Radio className="size-4" aria-hidden />}
              loading={stats.isPending}
            />
            <Stat
              label="Agents"
              value={number(s?.agents)}
              icon={<Users className="size-4" aria-hidden />}
              loading={stats.isPending}
            />
            <Stat
              label="Vouchers issued"
              value={number(s?.vouchers)}
              icon={<Ticket className="size-4" aria-hidden />}
              loading={stats.isPending}
            />
          </div>
          <Section
            title="Revenue"
            description="Successful transactions across all tenants, by source."
            className="mt-6"
          >
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <Stat
                label="Voucher sales"
                value={s ? formatKobo(s.successful_payment_amount) : '—'}
                hint={s ? `${s.pending_payments.toLocaleString()} pending` : undefined}
                icon={<Wallet className="size-4" aria-hidden />}
                loading={stats.isPending}
                tone={s && s.pending_payments > 0 ? 'warning' : 'default'}
              />
              <Stat
                label="Agent wallet top-ups"
                value={s ? formatKobo(s.successful_wallet_funding_amount) : '—'}
                loading={stats.isPending}
              />
              <Stat
                label="Subscriptions"
                value={s ? formatKobo(s.successful_subscription_amount) : '—'}
                loading={stats.isPending}
              />
            </div>
          </Section>
        </>
      )}
      <Section
        title="Newest tenants"
        className="mt-6"
        actions={
          <ButtonLink to="/platform/tenants" variant="secondary" size="sm">
            All tenants
          </ButtonLink>
        }
      >
        {recent.isPending ? (
          <div
            className="h-40 animate-pulse rounded-card border border-border bg-surface"
            aria-busy
          />
        ) : recent.isError ? (
          <ErrorState
            error={recent.error}
            onRetry={() => void recent.refetch()}
            title="Could not load tenants"
          />
        ) : recent.data.results.length === 0 ? (
          <p className="text-sm text-ink-500">No operator tenants yet.</p>
        ) : (
          <ul className="divide-y divide-border rounded-card border border-border bg-surface">
            {recent.data.results.map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <ButtonLink
                    to={`/platform/tenants/${t.id}`}
                    variant="link"
                    className="font-medium"
                  >
                    {t.name}
                  </ButtonLink>
                  <div className="truncate text-xs text-ink-500">
                    /s/{t.slug} · {t.member_count} member{t.member_count === 1 ? '' : 's'} ·{' '}
                    {t.voucher_count.toLocaleString()} vouchers
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <time
                    dateTime={t.created_at}
                    title={formatDateTime(t.created_at)}
                    className="hidden text-xs text-ink-500 sm:block"
                  >
                    {formatRelative(t.created_at)}
                  </time>
                  <StatusBadge status={t.is_active ? 'active' : 'inactive'} size="sm" />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <QuickLink
          to="/platform/routers"
          title="Router fleet"
          text="Every router across tenants with onboarding state."
        />
        <QuickLink
          to="/platform/payments"
          title="Payments"
          text="Voucher sales, wallet top-ups and subscriptions."
        />
        <QuickLink
          to="/platform/staff"
          title="Staff access"
          text="Invite support staff and manage their grants."
        />
      </div>
    </>
  );
}

function QuickLink({ to, title, text }: { to: string; title: string; text: string }) {
  return (
    <ButtonLink
      to={to}
      variant="secondary"
      className="h-auto flex-col items-start gap-1 px-4 py-3 text-left"
    >
      <span className="font-medium text-brand-950">{title}</span>
      <span className="text-xs font-normal text-ink-500">{text}</span>
    </ButtonLink>
  );
}
