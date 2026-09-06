import { Checkbox } from '@/components/ui';
import type { StaffService } from '@/types/api';
import { SERVICE_GROUPS } from '../platformVocabulary';

/** Grouped checklist of staff service grants; controlled by the parent form. */
export function ServicesField({
  value,
  onChange,
  error,
  disabled,
  legend = 'Services',
}: {
  value: readonly StaffService[];
  onChange: (next: StaffService[]) => void;
  error?: string | undefined;
  disabled?: boolean;
  legend?: string;
}) {
  const selected = new Set(value);
  function toggle(service: StaffService, checked: boolean) {
    const next = new Set(selected);
    if (checked) next.add(service);
    else next.delete(service);
    onChange(
      SERVICE_GROUPS.flatMap((g) => g.services.map((s) => s.value)).filter((s) => next.has(s)),
    );
  }
  return (
    <fieldset className="min-w-0" aria-invalid={error ? true : undefined}>
      <legend className="text-ink-800 mb-2 text-sm font-medium">
        {legend}{' '}
        <span className="text-danger-600" aria-hidden>
          *
        </span>
      </legend>
      <div className="grid gap-3 sm:grid-cols-2">
        {SERVICE_GROUPS.map((group) => (
          <div key={group.label} className="rounded-control border border-border p-3">
            <p className="mb-2 text-xs font-semibold tracking-wide text-ink-500 uppercase">
              {group.label}
            </p>
            <div className="flex flex-col gap-2">
              {group.services.map((s) => (
                <Checkbox
                  key={s.value}
                  label={s.label}
                  description={s.hint}
                  checked={selected.has(s.value)}
                  disabled={disabled}
                  onChange={(e) => toggle(s.value, e.target.checked)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
      {error && (
        <p role="alert" className="mt-1.5 text-xs text-danger-600">
          {error}
        </p>
      )}
    </fieldset>
  );
}
