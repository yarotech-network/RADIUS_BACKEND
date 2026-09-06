import { Dialog } from '@/components/ui';
import type { InternetPlan } from '@/types/api';
import { PlanForm } from './PlanForm';

export function PlanDialog({
  open,
  plan,
  onClose,
  onSaved,
}: {
  open: boolean;
  plan?: InternetPlan;
  onClose: () => void;
  onSaved: (plan: InternetPlan) => void;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      variant="drawer"
      size="md"
      title={plan ? `Edit ${plan.name}` : 'New plan'}
      description={
        plan
          ? 'Changes apply to vouchers generated from now on.'
          : 'Plans define what a voucher gives the customer.'
      }
    >
      {open && <PlanForm {...(plan ? { plan } : {})} onSaved={onSaved} onCancel={onClose} />}
    </Dialog>
  );
}
