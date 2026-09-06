import { useState } from 'react';
import { Download, MoreHorizontal, Plus, Radio, Ticket, Wallet } from 'lucide-react';
import {
  Avatar,
  Badge,
  Button,
  Card,
  CardHeader,
  Checkbox,
  ConfirmDialog,
  CopyButton,
  DescriptionList,
  Dialog,
  FormField,
  Input,
  Menu,
  SegmentedControl,
  Select,
  Skeleton,
  SkeletonText,
  Spinner,
  Stat,
  Switch,
  Tabs,
  Textarea,
  Tooltip,
} from '@/components/ui';
import { Alert, EmptyState, ErrorState, useToast } from '@/components/feedback';
import { DataTable, FilterBar, Pagination, SearchInput, type Column } from '@/components/data';
import { PageHeader, Section, StatusBadge } from '@/components/layout';
import { ApiError } from '@/services/api/errors';
import {
  formatBytes,
  formatDateTime,
  formatDuration,
  formatHours,
  formatKobo,
  formatRelative,
} from '@/lib/formatting';

interface DemoRow {
  id: number;
  username: string;
  plan: string;
  status: string;
  price: number;
  created_at: string;
}

const DEMO_NOW = Date.now();

const ROWS: DemoRow[] = Array.from({ length: 6 }).map((_, i) => ({
  id: i + 1,
  username: `YR${(48210 + i * 37).toString()}`,
  plan: ['Daily 1GB', 'Weekly Unlimited', 'Monthly 20GB'][i % 3]!,
  status: ['unused', 'active', 'expired', 'disabled'][i % 4]!,
  price: [50_000, 250_000, 800_000][i % 3]!,
  created_at: new Date(DEMO_NOW - i * 3_600_000 * 7).toISOString(),
}));

const STATUSES = [
  'unused',
  'active',
  'expired',
  'disabled',
  'pending',
  'success',
  'failed',
  'abandoned',
  'fulfilled',
  'paid_unfulfilled',
  'unverified',
  'not_requested',
  'sending',
  'accepted',
  'unknown',
  'suspended',
  'reviewed',
  'approved',
  'waiting_for_vpn',
  'vpn_failed',
  'testing_radius',
  'radius_failed',
  'accounting_failed',
  'not_deployed',
  'deploying',
  'deployed',
  'running',
  'succeeded',
  'trial',
  'cancelled',
  'revoked',
];

export default function UiGalleryPage() {
  const toast = useToast();
  const [dialog, setDialog] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [checked, setChecked] = useState(true);
  const [tab, setTab] = useState<'all' | 'unused' | 'active'>('all');
  const [segment, setSegment] = useState<'table' | 'cards'>('table');
  const [search, setSearch] = useState('');
  const [ordering, setOrdering] = useState<string | undefined>('-created_at');
  const [page, setPage] = useState(1);
  const [tableState, setTableState] = useState<'data' | 'loading' | 'empty' | 'error'>('data');

  const columns: Column<DemoRow>[] = [
    {
      key: 'username',
      header: 'Voucher',
      primary: true,
      cell: (r) => <span className="font-mono">{r.username}</span>,
    },
    { key: 'plan', header: 'Plan', cell: (r) => r.plan },
    {
      key: 'status',
      header: 'Status',
      sortField: 'status',
      cell: (r) => <StatusBadge status={r.status} />,
    },
    {
      key: 'price',
      header: 'Price',
      align: 'right',
      hideBelow: 'lg',
      cell: (r) => <span className="tabular">{formatKobo(r.price, { compact: true })}</span>,
    },
    {
      key: 'created',
      header: 'Created',
      sortField: 'created_at',
      hideBelow: 'md',
      cell: (r) => <span title={formatDateTime(r.created_at)}>{formatRelative(r.created_at)}</span>,
    },
  ];

  const apiError = new ApiError({
    status: 503,
    message: 'RADIUS accounting database is unavailable.',
  });

  return (
    <div className="mx-auto max-w-6xl space-y-10 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title="UI gallery"
        description="Development-only reference of every primitive. Not part of the production bundle."
        crumbs={[{ label: 'Dev', to: '/__dev/ui' }, { label: 'UI gallery' }]}
        meta={<Badge tone="brand">dev</Badge>}
        actions={
          <>
            <Button variant="secondary" leadingIcon={<Download />}>
              Export
            </Button>
            <Button leadingIcon={<Plus />}>Primary action</Button>
          </>
        }
      />

      <Section title="Buttons">
        <Card>
          <div className="flex flex-wrap items-center gap-3">
            <Button>Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="danger">Danger</Button>
            <Button variant="link">Link</Button>
            <Button loading>Saving</Button>
            <Button disabled>Disabled</Button>
            <Button size="sm">Small</Button>
            <Button size="lg">Large</Button>
            <Button size="icon" variant="secondary" aria-label="More">
              <MoreHorizontal className="size-4" />
            </Button>
            <Tooltip content="Tooltips are CSS-only">
              <Button variant="ghost" size="sm">
                Hover me
              </Button>
            </Tooltip>
          </div>
        </Card>
      </Section>

      <Section title="Form controls">
        <Card>
          <div className="grid gap-5 sm:grid-cols-2">
            <FormField label="Username" hint="3–150 characters" required>
              <Input placeholder="e.g. shop-lagos-01" autoComplete="off" />
            </FormField>
            <FormField label="Email" error="Enter a valid email address">
              <Input type="email" defaultValue="not-an-email" />
            </FormField>
            <FormField label="Price" hint="Stored in kobo; you type naira">
              <Input inputMode="decimal" prefix="₦" placeholder="1,500" />
            </FormField>
            <FormField label="Plan" optionalLabel>
              <Select
                placeholder="Any plan"
                options={[
                  { value: '1', label: 'Daily 1GB' },
                  { value: '2', label: 'Weekly Unlimited' },
                ]}
              />
            </FormField>
            <FormField label="Address" className="sm:col-span-2">
              <Textarea placeholder="Street, city" />
            </FormField>
            <Checkbox
              label="Active"
              description="Inactive plans are hidden from the storefront."
              defaultChecked
            />
            <FormField label="Enable WhatsApp delivery" inline>
              <Switch
                checked={checked}
                onCheckedChange={setChecked}
                label="Enable WhatsApp delivery"
              />
            </FormField>
          </div>
        </Card>
      </Section>

      <Section
        title="Status vocabulary"
        description="One badge per backend enum value. Unknown values degrade to neutral."
      >
        <Card>
          <div className="flex flex-wrap gap-2">
            {STATUSES.map((s) => (
              <StatusBadge key={s} status={s} />
            ))}
            <StatusBadge status="brand_new_value" />
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Badge tone="brand">Brand</Badge>
            <Badge tone="outline">Outline</Badge>
            <Badge tone="info" size="sm">
              Small
            </Badge>
            <Avatar initials="AO" size="sm" />
            <Avatar initials="AO" />
            <Avatar initials="AO" size="lg" />
          </div>
        </Card>
      </Section>

      <Section title="Stats">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat
            label="Wallet balance"
            value={formatKobo(1_250_000)}
            tone="brand"
            icon={<Wallet />}
            hint="Updated just now"
          />
          <Stat label="Active vouchers" value="1,284" icon={<Ticket />} hint="of 5,120 total" />
          <Stat label="Routers online" value="—" icon={<Radio />} hint="Telemetry not available" />
          <Stat label="Pending payments" value="3" tone="warning" loading={false} />
          <Stat label="Loading" value="" loading />
        </div>
      </Section>

      <Section title="Feedback">
        <div className="grid gap-3 lg:grid-cols-2">
          <Alert tone="info" title="Heads up">
            Generated passwords are only visible on the printable sheet.
          </Alert>
          <Alert tone="success" title="Saved">
            Your changes were saved.
          </Alert>
          <Alert tone="warning" title="Replayed request">
            The server returned a previous result for this idempotency key.
          </Alert>
          <Alert
            tone="danger"
            title="Could not disconnect session"
            actions={
              <Button size="sm" variant="secondary">
                Retry
              </Button>
            }
          >
            RADIUS is not reachable right now.
          </Alert>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            onClick={() => toast.success('Vouchers generated', '25 vouchers added to the batch.')}
          >
            Success toast
          </Button>
          <Button
            variant="secondary"
            onClick={() => toast.error('Payment failed', 'Paystack returned an error. Try again.')}
          >
            Error toast
          </Button>
          <Button
            variant="secondary"
            onClick={() =>
              toast.toast({
                title: 'Router provisioning started',
                description: 'Track progress on the router page.',
                action: { label: 'View', onClick: () => undefined },
              })
            }
          >
            Toast with action
          </Button>
        </div>
        <div className="grid gap-3 lg:grid-cols-3">
          <Card padded={false}>
            <EmptyState
              title="No vouchers yet"
              description="Generate a batch to get started."
              action={
                <Button size="sm" leadingIcon={<Plus />}>
                  Generate
                </Button>
              }
              compact
            />
          </Card>
          <Card padded={false}>
            <ErrorState error={apiError} onRetry={() => undefined} compact />
          </Card>
          <Card padded={false}>
            <ErrorState
              error={
                new ApiError({ status: 403, message: 'You do not have permission to do this.' })
              }
              compact
            />
          </Card>
        </div>
        <div className="flex items-center gap-4">
          <Spinner />
          <Skeleton className="h-8 w-40" />
          <SkeletonText className="w-56" />
        </div>
      </Section>

      <Section title="Overlays">
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => setDialog(true)}>
            Open dialog
          </Button>
          <Button variant="secondary" onClick={() => setDrawer(true)}>
            Open drawer
          </Button>
          <Button variant="danger" onClick={() => setConfirm(true)}>
            Destructive confirm
          </Button>
          <Menu
            trigger={(props) => (
              <Button variant="secondary" trailingIcon={<MoreHorizontal />} {...props}>
                Menu
              </Button>
            )}
            items={[
              { key: 'edit', label: 'Edit', onSelect: () => toast.info('Edit') },
              { key: 'print', label: 'Print', onSelect: () => toast.info('Print') },
              'separator',
              {
                key: 'disable',
                label: 'Disable',
                tone: 'danger',
                onSelect: () => toast.info('Disable'),
              },
            ]}
          />
          <CopyButton value="YR48210" label="Copy username" />
        </div>
        <Dialog
          open={dialog}
          onClose={() => setDialog(false)}
          title="Generate vouchers"
          description="Creates up to 100 vouchers for one plan."
          footer={
            <>
              <Button variant="secondary" onClick={() => setDialog(false)}>
                Cancel
              </Button>
              <Button onClick={() => setDialog(false)}>Generate</Button>
            </>
          }
        >
          <div className="space-y-4">
            <FormField label="Plan" required>
              <Select
                placeholder="Choose a plan"
                options={[{ value: '1', label: 'Daily 1GB — ₦500' }]}
              />
            </FormField>
            <FormField label="Quantity" hint="1–100" required>
              <Input type="number" defaultValue={25} />
            </FormField>
          </div>
        </Dialog>
        <Dialog
          variant="drawer"
          open={drawer}
          onClose={() => setDrawer(false)}
          title="Router details"
          description="mikrotik-abuja-01"
          size="md"
        >
          <DescriptionList
            items={[
              { label: 'IP address', value: '10.100.100.12', mono: true },
              { label: 'State', value: <StatusBadge status="waiting_for_vpn" /> },
              { label: 'Last seen', value: formatRelative(new Date(DEMO_NOW - 90_000)) },
              { label: 'Location', value: 'Wuse 2, Abuja' },
              { label: 'WireGuard public key', value: 'nQd7…Kx0=', mono: true, span: 2 },
            ]}
          />
        </Dialog>
        <ConfirmDialog
          open={confirm}
          onClose={() => setConfirm(false)}
          onConfirm={() => new Promise((r) => setTimeout(r, 600))}
          title="Disable voucher YR48210?"
          description="The customer will be disconnected immediately. This cannot be undone."
          confirmLabel="Disable voucher"
          tone="danger"
          typeToConfirm="YR48210"
        />
      </Section>

      <Section
        title="Data table"
        description="Sorting only on fields the backend orders by; table on desktop, cards on mobile."
      >
        <FilterBar
          search={
            <SearchInput value={search} onChange={setSearch} placeholder="Search vouchers…" />
          }
          filters={
            <>
              <Select
                size="sm"
                className="w-40"
                placeholder="Any status"
                options={['unused', 'active', 'expired', 'disabled'].map((s) => ({
                  value: s,
                  label: s,
                }))}
              />
              <SegmentedControl
                size="sm"
                value={tableState}
                onChange={setTableState}
                options={[
                  { value: 'data', label: 'Data' },
                  { value: 'loading', label: 'Loading' },
                  { value: 'empty', label: 'Empty' },
                  { value: 'error', label: 'Error' },
                ]}
              />
            </>
          }
          activeCount={search ? 1 : 0}
          onClear={() => setSearch('')}
          actions={
            <SegmentedControl
              size="sm"
              value={segment}
              onChange={setSegment}
              options={[
                { value: 'table', label: 'Table' },
                { value: 'cards', label: 'Cards' },
              ]}
            />
          }
        />
        <Tabs
          value={tab}
          onChange={setTab}
          items={[
            { value: 'all', label: 'All', count: 5120 },
            { value: 'unused', label: 'Unused', count: 812 },
            { value: 'active', label: 'Active', count: 1284 },
          ]}
        />
        <DataTable
          columns={columns}
          rows={
            tableState === 'data'
              ? ROWS.filter((r) => r.username.toLowerCase().includes(search.toLowerCase()))
              : tableState === 'empty'
                ? []
                : undefined
          }
          loading={tableState === 'loading'}
          error={tableState === 'error' ? apiError : undefined}
          onRetry={() => setTableState('data')}
          rowKey={(r) => r.id}
          ordering={ordering}
          onOrderingChange={setOrdering}
          onRowClick={(r) => toast.info(`Open ${r.username}`)}
          rowActions={() => (
            <Button size="icon" variant="ghost" aria-label="Row actions">
              <MoreHorizontal className="size-4" />
            </Button>
          )}
          empty={
            <EmptyState title="No vouchers match" description="Try a different search." compact />
          }
          mobileCards={segment === 'cards'}
        />
        <Pagination
          count={5120}
          page={page}
          totalPages={256}
          pageSize={20}
          onPageChange={setPage}
          onPageSizeChange={() => undefined}
          itemLabel="vouchers"
        />
      </Section>

      <Section title="Formatters">
        <Card>
          <CardHeader title="lib/formatting" description="Kobo, dates, bytes and durations." />
          <DescriptionList
            columns={3}
            items={[
              { label: 'formatKobo(1250050)', value: formatKobo(1_250_050), mono: true },
              {
                label: 'formatKobo(50000, compact)',
                value: formatKobo(50_000, { compact: true }),
                mono: true,
              },
              { label: 'formatBytes(1536000000)', value: formatBytes(1_536_000_000), mono: true },
              { label: 'formatDuration(93784)', value: formatDuration(93_784), mono: true },
              { label: 'formatHours(168)', value: formatHours(168), mono: true },
              {
                label: 'formatRelative(-3h)',
                value: formatRelative(new Date(DEMO_NOW - 3 * 3_600_000)),
                mono: true,
              },
            ]}
          />
        </Card>
      </Section>
    </div>
  );
}
