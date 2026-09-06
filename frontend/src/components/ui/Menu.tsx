import { useEffect, useId, useRef, useState, type ReactNode, type RefObject } from 'react';
import { cn } from '@/lib/utilities/cn';

export interface MenuItem {
  key: string;
  label: ReactNode;
  icon?: ReactNode;
  onSelect?: () => void;
  href?: string;
  tone?: 'default' | 'danger';
  disabled?: boolean;
  hidden?: boolean;
}

export interface MenuProps {
  trigger: (props: {
    'aria-expanded': boolean;
    'aria-haspopup': 'menu';
    'aria-controls': string;
    onClick: () => void;
    ref: RefObject<HTMLButtonElement | null>;
  }) => ReactNode;
  items: (MenuItem | 'separator')[];
  align?: 'start' | 'end';
  className?: string | undefined;
}

/** Lightweight dropdown menu with roving focus, ESC/outside-click dismissal. */
export function Menu({ trigger, items, align = 'end', className }: MenuProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const visible = items.filter((i) => i === 'separator' || !i.hidden);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node;
      if (!listRef.current?.contains(target) && !triggerRef.current?.contains(target))
        setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus();
      }
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        const buttons = Array.from(
          listRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])') ?? [],
        );
        if (buttons.length === 0) return;
        event.preventDefault();
        const index = buttons.findIndex((b) => b === document.activeElement);
        const next =
          event.key === 'ArrowDown'
            ? (index + 1) % buttons.length
            : (index - 1 + buttons.length) % buttons.length;
        buttons[next]?.focus();
      }
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('touchstart', onPointer);
    document.addEventListener('keydown', onKey);
    const first = listRef.current?.querySelector<HTMLElement>('[role="menuitem"]:not([disabled])');
    first?.focus();
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('touchstart', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className={cn('relative inline-flex', className)}>
      {trigger({
        'aria-expanded': open,
        'aria-haspopup': 'menu',
        'aria-controls': id,
        onClick: () => setOpen((v) => !v),
        ref: triggerRef,
      })}
      {open && (
        <div
          ref={listRef}
          id={id}
          role="menu"
          className={cn(
            'absolute top-full z-40 mt-1 min-w-44 rounded-control border border-border bg-surface p-1 shadow-floating',
            align === 'end' ? 'right-0' : 'left-0',
          )}
        >
          {visible.map((item, index) =>
            item === 'separator' ? (
              <div key={`sep-${index}`} role="separator" className="my-1 h-px bg-border" />
            ) : (
              <button
                key={item.key}
                role="menuitem"
                type="button"
                disabled={item.disabled}
                onClick={() => {
                  setOpen(false);
                  item.onSelect?.();
                }}
                className={cn(
                  'flex w-full items-center gap-2 rounded-[6px] px-2.5 py-2 text-left text-sm transition-colors',
                  'hover:bg-slate-100 focus:bg-slate-100 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50',
                  item.tone === 'danger' ? 'text-danger-700' : 'text-ink-900',
                )}
              >
                {item.icon && (
                  <span className="inline-flex text-ink-500 [&>svg]:size-4">{item.icon}</span>
                )}
                {item.label}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  );
}
