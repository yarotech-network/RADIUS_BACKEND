import { Link } from 'react-router';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Banknote,
  Layers,
  Radio,
  Ticket,
  Users,
} from 'lucide-react';
import { PageHeader } from '@/components/layout';
import { ButtonLink, Card, Stat } from '@/components/ui';
import { Alert, ErrorState } from '@/components/feedback';
import { formatKobo } from '@/lib/formatting/money';
import { formatNumber } from '@/lib/formatting/units';
import { formatRelative } from '@/lib/formatting/dates';
import { can } from '@/services/auth/principal';
import { usePrincipal } from '@/app/auth/useAuth';
import { workspaceName } from '@/services/auth/principal';
import { DASHBOARD_LIVE_PARAMS, useDashboardStats, useLiveUsers } from '../queries';

export default function DashboardPage() {
  const principal = usePrincipal();
  const stats = useDashboardStats();
  const canSessions = can(principal, 'sessions.view');
  const live = useLiveUsers(DASHBOARD_LIVE_PARAMS, { live: canSessions });
  const name = workspaceName(principal);
  const s = stats.data;

  return (
    <>
      <PageHeader
        title={name ? `${name} overview` : 'Overview'}
        description={
          s ? `Updated ${formatRelative(s.observed_at)}` : 'Live totals for your hotspot business.'
        }
        actions={
          can(principal, 'vouchers.generate') ? (
            <ButtonLink to="/vouchers/generate">Generate vouchers</ButtonLink>
          ) : undefined
        }
      />

      {stats.isError && !s ? (
        <ErrorState
          error={stats.error}
          onRetry={() => void stats.refetch()}
          title="Dashboard could not be loaded"
        />
      ) : (
        <>
          {s && s.paid_unfulfilled_payments > 0 && can(principal, 'payments.recovery.view') && (
            <Alert
              tone="warning"
              className="mb-4"
              title={`${s.paid_unfulfilled_payments} paid ${s.paid_unfulfilled_payments === 1 ? 'order has' : 'orders have'} no voucher yet`}
              actions={
                <ButtonLink to="/payments/recovery" size="sm" variant="secondary">
                  Review
                </ButtonLink>
              }
            >
              Customers paid but delivery failed. Fulfil or refund them from Payments → Recovery.
            </Alert>
          )}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 md:gap-4 xl:grid-cols-6">
            <Stat
              label="Revenue"
              value={s ? formatKobo(s.total_revenue) : '—'}
              hint="Successful online payments"
              icon={<Banknote className="h-4 w-4" aria-hidden />}
              loading={stats.isPending}
              tone="brand"
            />
            <Stat
              label="Active vouchers"
              value={s ? formatNumber(s.active_vouchers) : '—'}
              hint={s ? `of ${formatNumber(s.total_vouchers)} issued` : undefined}
              icon={<Ticket className="h-4 w-4" aria-hidden />}
              loading={stats.isPending}
            />
            <Stat
              label="Online now"
              value={canSessions ? (live.data ? formatNumber(live.data.count) : '—') : 'n/a'}
              hint={canSessions ? 'Live sessions' : 'No access'}
              icon={<Activity className="h-4 w-4" aria-hidden />}
              loading={canSessions && live.isPending}
            />
            <Stat
              label="Routers"
              value={s ? `${formatNumber(s.active_routers)}/${formatNumber(s.total_routers)}` : '—'}
              hint="Active / registered"
              icon={<Radio className="h-4 w-4" aria-hidden />}
              loading={stats.isPending}
            />
            <Stat
              label="Agents"
              value={s ? formatNumber(s.total_agents) : '—'}
              hint="Resellers"
              icon={<Users className="h-4 w-4" aria-hidden />}
              loading={stats.isPending}
            />
            <Stat
              label="Pending payments"
              value={s ? formatNumber(s.pending_payments) : '—'}
              hint="Awaiting Paystack"
              icon={<AlertTriangle className="h-4 w-4" aria-hidden />}
              loading={stats.isPending}
              tone={s && s.pending_payments > 0 ? 'warning' : 'default'}
            />
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <QuickLink
              to="/vouchers"
              icon={<Ticket className="h-5 w-5" aria-hidden />}
              title="Vouchers"
              description="Find a code, check its status, print or disable it."
            />
            {canSessions && (
              <QuickLink
                to="/sessions"
                icon={<Activity className="h-5 w-5" aria-hidden />}
                title="Live sessions"
                description="Who is connected right now, and disconnect abusers."
              />
            )}
            {can(principal, 'plans.view') && (
              <QuickLink
                to="/plans"
                icon={<Layers className="h-5 w-5" aria-hidden />}
                title="Plans"
                description="Prices, speeds and durations customers can buy."
              />
            )}
          </div>
          <p className="mt-6 text-xs text-ink-500">
            Trends over time are not available from the API yet — totals shown are cumulative.
          </p>
        </>
      )}
    </>
  );
}

function QuickLink({
  to,
  icon,
  title,
  description,
}: {
  to: string;
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <Card className="group transition-colors hover:border-brand-300" padded={false}>
      <Link
        to={to}
        className="flex items-start gap-3 p-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
      >
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-control bg-brand-50 text-brand-700">
          {icon}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block font-medium text-ink-900">{title}</span>
          <span className="block text-sm text-ink-600">{description}</span>
        </span>
        <ArrowRight
          className="mt-1 h-4 w-4 shrink-0 text-ink-400 transition-transform group-hover:translate-x-0.5"
          aria-hidden
        />
      </Link>
    </Card>
  );
}
