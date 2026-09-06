import { Badge } from '@/components/ui';
import { serviceLabel } from '../platformVocabulary';

/** Compact list of granted services. */
export function ServiceChips({ services, max = 4 }: { services: readonly string[]; max?: number }) {
  if (services.length === 0) return <span className="text-xs text-ink-400">No services</span>;
  const shown = services.slice(0, max);
  const rest = services.length - shown.length;
  return (
    <span className="inline-flex flex-wrap gap-1" title={services.map(serviceLabel).join(', ')}>
      {shown.map((s) => (
        <Badge key={s} tone="neutral" size="sm">
          {serviceLabel(s)}
        </Badge>
      ))}
      {rest > 0 && (
        <Badge tone="neutral" size="sm">
          +{rest} more
        </Badge>
      )}
    </span>
  );
}
