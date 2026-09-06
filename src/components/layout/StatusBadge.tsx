import { Badge } from '@/components/ui/Badge';
import { statusLabel, statusTone } from './statusVocabulary';

export function StatusBadge({
  status,
  size,
  dot = true,
  className,
}: {
  status: string | null | undefined;
  size?: 'sm' | 'md';
  dot?: boolean;
  className?: string;
}) {
  if (!status) return <span className="text-ink-400">—</span>;
  return (
    <Badge
      tone={statusTone(status)}
      dot={dot}
      {...(size ? { size } : {})}
      {...(className ? { className } : {})}
    >
      {statusLabel(status)}
    </Badge>
  );
}

export function BooleanBadge({
  value,
  trueLabel = 'Active',
  falseLabel = 'Inactive',
  size,
}: {
  value: boolean;
  trueLabel?: string;
  falseLabel?: string;
  size?: 'sm' | 'md';
}) {
  return (
    <Badge tone={value ? 'success' : 'neutral'} dot {...(size ? { size } : {})}>
      {value ? trueLabel : falseLabel}
    </Badge>
  );
}
