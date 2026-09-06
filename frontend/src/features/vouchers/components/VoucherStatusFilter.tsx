import { Tabs } from '@/components/ui';
import type { VoucherStatus } from '@/types/api';

export type VoucherStatusTab = 'all' | VoucherStatus;

const TABS: { value: VoucherStatusTab; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'unused', label: 'Unused' },
  { value: 'active', label: 'Active' },
  { value: 'expired', label: 'Expired' },
  { value: 'disabled', label: 'Disabled' },
];

export function VoucherStatusFilter({
  value,
  onChange,
}: {
  value: VoucherStatusTab;
  onChange: (v: VoucherStatusTab) => void;
}) {
  return <Tabs items={TABS} value={value} onChange={onChange} ariaLabel="Voucher status" />;
}
