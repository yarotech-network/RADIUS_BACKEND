import { useState } from 'react';
import { Link, useParams } from 'react-router';
import { CheckCircle2, PauseCircle, Pencil, Ticket } from 'lucide-react';
import { PageHeader, StatusBadge } from '@/components/layout';
import {
  Button,
  Card,
  ConfirmDialog,
  DescriptionList,
  Skeleton,
  Stat,
  Tabs,
} from '@/components/ui';
import { Alert, EmptyState, QueryBoundary, useToast } from '@/components/feedback';
import { DataTable, Pagination, type Column } from '@/components/data';
import { formatDateTime, formatRelative } from '@/lib/formatting/dates';
import { formatKobo } from '@/lib/formatting/money';
import type { AgentProfile, Voucher } from '@/types/api';
import { useVouchers } from '@/features/vouchers/queries';
import { useAgent, useApproveAgent, useSuspendAgent } from '../queries';
import { AGENT_STATUS_LABELS, canApprove, canSuspend } from '../agentRules';
import { formatCommission } from '../agentSchemas';
import { EditAgentDialog } from '../components/AgentForms';

type Tab = 'overview' | 'sales';

export default function AgentDetailPage() {
  const { id = '' } = useParams();
  const query = useAgent(Number(id));
  return (
    <QueryBoundary
      query={query}
      errorTitle="Agent not found"
      skeleton={
        <>
          <PageHeader title={<Skeleton className="h-7 w-48" />} backTo="/agents" />
          <Card>
            <Skeleton className="h-32 w-full" />
          </Card>
        </>
      }
    >
      {(agent) => <AgentDetail agent={agent} />}
    </QueryBoundary>
  );
}

function AgentDetail({ agent }: { agent: AgentProfile }) {
  const toast = useToast();
  const approve = useApproveAgent();
  const suspend = useSuspendAgent();
  const [tab, setTab] = useState<Tab>('overview');
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState<'approve' | 'suspend' | null>(null);

  return (
    <>
      <PageHeader
        backTo="/agents"
        crumbs={[{ label: 'Agents', to: '/agents' }, { label: agent.username }]}
        title={
          <span className="inline-flex flex-wrap items-center gap-3">
            {agent.username}
            <StatusBadge status={agent.status} size="md" />
          </span>
        }
        description={agent.shop_name || 'No shop name'}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              leadingIcon={<Pencil className="h-4 w-4" aria-hidden />}
              onClick={() => setEditing(true)}
            >
              Edit
            </Button>
            {canApprove(agent.status) && (
              <Button
                leadingIcon={<CheckCircle2 className="h-4 w-4" aria-hidden />}
                onClick={() => setConfirm('approve')}
              >
                {agent.status === 'suspended' ? 'Re-activate' : 'Approve'}
              </Button>
            )}
            {canSuspend(agent.status) && (
              <Button
                variant="danger"
                leadingIcon={<PauseCircle className="h-4 w-4" aria-hidden />}
                onClick={() => setConfirm('suspend')}
              >
                Suspend
              </Button>
            )}
          </div>
        }
      />

      {agent.status === 'pending' && (
        <Alert tone="info" className="mb-4" title="Awaiting approval">
          This agent cannot sign in to the agent portal until you approve them.
        </Alert>
      )}
      {agent.status === 'suspended' && (
        <Alert tone="warning" className="mb-4" title="Suspended">
          The agent is locked out of the portal. Their wallet balance is preserved.
        </Alert>
      )}

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Stat
          label="Wallet balance"
          value={formatKobo(agent.wallet_balance)}
          hint="Prepaid credit for voucher sales"
        />
        <Stat
          label="Commission"
          value={`${formatCommission(agent.commission_rate)}%`}
          hint="Of each sale"
        />
        <Stat
          label="Status"
          value={AGENT_STATUS_LABELS[agent.status]}
          hint={`Joined ${formatRelative(agent.created_at)}`}
        />
      </div>

      <Tabs
        items={[
          { value: 'overview', label: 'Profile' },
          { value: 'sales', label: 'Vouchers sold' },
        ]}
        value={tab}
        onChange={setTab}
        ariaLabel="Agent sections"
        className="mb-4"
      />
      <Card>
        {tab === 'overview' && (
          <DescriptionList
            columns={2}
            items={[
              { label: 'Username', value: agent.username, mono: true },
              { label: 'Phone', value: agent.phone, mono: true },
              { label: 'Shop name', value: agent.shop_name || null },
              { label: 'Commission rate', value: `${formatCommission(agent.commission_rate)}%` },
              { label: 'Joined', value: formatDateTime(agent.created_at) },
              {
                label: 'Wallet',
                value:
                  agent.wallet_balance === null
                    ? 'No wallet yet'
                    : formatKobo(agent.wallet_balance),
              },
            ]}
          />
        )}
        {tab === 'sales' && <AgentSales agent={agent} />}
      </Card>

      <EditAgentDialog
        agent={agent}
        open={editing}
        onClose={() => setEditing(false)}
        onSaved={(saved) => {
          setEditing(false);
          toast.success('Agent updated', `${saved.username} saved.`);
        }}
      />
      <ConfirmDialog
        open={confirm !== null}
        onClose={() => setConfirm(null)}
        tone={confirm === 'suspend' ? 'danger' : 'default'}
        title={
          confirm === 'suspend'
            ? `Suspend ${agent.username}?`
            : `${agent.status === 'suspended' ? 'Re-activate' : 'Approve'} ${agent.username}?`
        }
        description={
          confirm === 'suspend'
            ? 'The agent is signed out of the portal and cannot sell vouchers until re-activated. Wallet funds are kept.'
            : 'The agent can sign in to the agent portal, fund their wallet and sell vouchers.'
        }
        confirmLabel={
          confirm === 'suspend'
            ? 'Suspend agent'
            : agent.status === 'suspended'
              ? 'Re-activate agent'
              : 'Approve agent'
        }
        onConfirm={async () => {
          const result =
            confirm === 'suspend'
              ? await suspend.mutateAsync(agent.id)
              : await approve.mutateAsync(agent.id);
          toast.success(`Agent ${AGENT_STATUS_LABELS[result.status].toLowerCase()}`);
        }}
      />
    </>
  );
}

/** Vouchers this agent generated — the voucher list supports `search=<agent username>` (gap: no dedicated agent filter). */
function AgentSales({ agent }: { agent: AgentProfile }) {
  const [page, setPage] = useState(1);
  const query = useVouchers({
    search: agent.username,
    page,
    page_size: 20,
    ordering: '-created_at',
  });
  const columns: Column<Voucher>[] = [
    {
      key: 'code',
      header: 'Voucher',
      primary: true,
      cell: (v) => (
        <Link
          to={`/vouchers/${v.id}`}
          className="font-mono text-sm font-semibold text-brand-700 hover:underline"
          onClick={(e) => e.stopPropagation()}
        >
          {v.username}
        </Link>
      ),
    },
    { key: 'plan', header: 'Plan', cell: (v) => v.plan_name },
    { key: 'status', header: 'Status', cell: (v) => <StatusBadge status={v.status} size="sm" /> },
    {
      key: 'price',
      header: 'Price',
      align: 'right',
      hideBelow: 'md',
      cell: (v) => <span className="tabular-nums">{v.price_display}</span>,
    },
    {
      key: 'created',
      header: 'Sold',
      hideBelow: 'lg',
      cell: (v) => (
        <time dateTime={v.created_at} title={formatDateTime(v.created_at)}>
          {formatRelative(v.created_at)}
        </time>
      ),
    },
  ];
  // The search also matches voucher codes containing the username; keep only this agent's rows.
  const rows = query.data?.results.filter((v) => v.agent === agent.id);
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink-600">Vouchers generated by this agent from their wallet.</p>
      <DataTable
        caption="Vouchers sold"
        columns={columns}
        rows={rows}
        rowKey={(v) => v.id}
        loading={query.isPending}
        refreshing={query.isFetching && !query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        dense
        empty={
          <EmptyState
            compact
            icon={<Ticket className="h-6 w-6" aria-hidden />}
            title="No sales yet"
            description="Vouchers the agent generates will be listed here."
          />
        }
      />
      {query.data && query.data.total_pages > 1 && (
        <Pagination
          count={query.data.count}
          page={query.data.current_page}
          totalPages={query.data.total_pages}
          pageSize={20}
          onPageChange={setPage}
          itemLabel="vouchers"
        />
      )}
    </div>
  );
}
