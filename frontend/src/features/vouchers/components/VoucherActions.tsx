import { Ban, Eye, MoreHorizontal, Pencil, Printer, Trash2 } from 'lucide-react';
import { Button, Menu } from '@/components/ui';
import { can } from '@/services/auth/principal';
import { usePrincipal } from '@/app/auth/useAuth';
import type { Voucher } from '@/types/api';
import { canDisable, isEditable } from '../voucherRules';

export interface VoucherActionHandlers {
  onPrint?: (voucher: Voucher) => void;
  onDisable?: (voucher: Voucher) => void;
  onEdit?: (voucher: Voucher) => void;
  onDelete?: (voucher: Voucher) => void;
}

/** Row-level menu; capability + state aware so users only see actions that can succeed. */
export function VoucherActions({
  voucher,
  handlers,
  includeView = true,
}: {
  voucher: Voucher;
  handlers: VoucherActionHandlers;
  includeView?: boolean;
}) {
  const principal = usePrincipal();
  const items = [
    ...(includeView
      ? [
          {
            key: 'view',
            label: 'View details',
            icon: <Eye className="h-4 w-4" aria-hidden />,
            href: `/vouchers/${voucher.id}`,
          },
        ]
      : []),
    ...(can(principal, 'vouchers.print') && handlers.onPrint
      ? [
          {
            key: 'print',
            label: 'Print credentials',
            icon: <Printer className="h-4 w-4" aria-hidden />,
            onSelect: () => handlers.onPrint?.(voucher),
          },
        ]
      : []),
    ...(can(principal, 'vouchers.manage') && isEditable(voucher) && handlers.onEdit
      ? [
          {
            key: 'edit',
            label: 'Edit',
            icon: <Pencil className="h-4 w-4" aria-hidden />,
            onSelect: () => handlers.onEdit?.(voucher),
          },
        ]
      : []),
    ...(can(principal, 'vouchers.manage') && canDisable(voucher) && handlers.onDisable
      ? [
          'separator' as const,
          {
            key: 'disable',
            label: 'Disable',
            icon: <Ban className="h-4 w-4" aria-hidden />,
            tone: 'danger' as const,
            onSelect: () => handlers.onDisable?.(voucher),
          },
        ]
      : []),
    ...(can(principal, 'vouchers.manage') && isEditable(voucher) && handlers.onDelete
      ? [
          {
            key: 'delete',
            label: 'Delete',
            icon: <Trash2 className="h-4 w-4" aria-hidden />,
            tone: 'danger' as const,
            onSelect: () => handlers.onDelete?.(voucher),
          },
        ]
      : []),
  ];
  if (items.length === 0) return null;
  return (
    <Menu
      trigger={(props) => (
        <Button
          {...props}
          variant="ghost"
          size="icon"
          aria-label={`Actions for ${voucher.username}`}
        >
          <MoreHorizontal className="h-4 w-4" aria-hidden />
        </Button>
      )}
      items={items}
    />
  );
}
