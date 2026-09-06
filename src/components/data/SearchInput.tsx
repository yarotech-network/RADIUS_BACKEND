import { useEffect, useState } from 'react';
import { Search, X } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { useDebouncedValue } from '@/lib/utilities/useDebouncedValue';

/** Search box that keeps a local draft and only reports debounced changes upward. */
export function SearchInput({
  value,
  onChange,
  placeholder = 'Search…',
  className,
  ariaLabel = 'Search',
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  ariaLabel?: string;
}) {
  const [draft, setDraft] = useState(value);
  const [syncedValue, setSyncedValue] = useState(value);
  // Adopt external resets (e.g. "Clear filters") without an effect.
  if (value !== syncedValue) {
    setSyncedValue(value);
    setDraft(value);
  }
  const debounced = useDebouncedValue(draft);

  useEffect(() => {
    if (debounced !== value) onChange(debounced);
    // Only fire when the debounced draft settles; `value`/`onChange` are read for comparison.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  return (
    <Input
      type="search"
      inputMode="search"
      aria-label={ariaLabel}
      placeholder={placeholder}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      leadingIcon={<Search />}
      className={className}
      trailingSlot={
        draft ? (
          <button
            type="button"
            aria-label="Clear search"
            onClick={() => {
              setDraft('');
              onChange('');
            }}
            className="rounded p-1.5 text-ink-400 hover:text-ink-900"
          >
            <X className="size-4" />
          </button>
        ) : undefined
      }
    />
  );
}
