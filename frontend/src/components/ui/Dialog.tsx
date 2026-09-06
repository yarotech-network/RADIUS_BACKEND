import { useEffect, useId, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utilities/cn';
import { Button } from './Button';

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  /** `dialog` = centred modal; `drawer` = right-side panel (full-screen on mobile). */
  variant?: 'dialog' | 'drawer';
  size?: 'sm' | 'md' | 'lg' | 'xl';
  /** Prevent closing while a mutation is running. */
  dismissible?: boolean;
  className?: string;
}

const SIZES = {
  sm: 'sm:max-w-sm',
  md: 'sm:max-w-lg',
  lg: 'sm:max-w-2xl',
  xl: 'sm:max-w-4xl',
} as const;
const DRAWER_SIZES = {
  sm: 'sm:max-w-sm',
  md: 'sm:max-w-md',
  lg: 'sm:max-w-xl',
  xl: 'sm:max-w-3xl',
} as const;

/**
 * Native <dialog>-based modal/drawer: browser-provided focus trap, ESC handling and top-layer stacking.
 */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  variant = 'dialog',
  size = 'md',
  dismissible = true,
  className,
}: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descId = useId();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const handleCancel = (event: Event) => {
      event.preventDefault();
      if (dismissible) onClose();
    };
    const handleClose = () => {
      if (open) onClose();
    };
    el.addEventListener('cancel', handleCancel);
    el.addEventListener('close', handleClose);
    return () => {
      el.removeEventListener('cancel', handleCancel);
      el.removeEventListener('close', handleClose);
    };
  }, [dismissible, onClose, open]);

  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  if (!open) return null;

  const isDrawer = variant === 'drawer';

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={description ? descId : undefined}
      onClick={(event) => {
        if (dismissible && event.target === event.currentTarget) onClose();
      }}
      className={cn(
        'bg-transparent p-0 backdrop:bg-brand-950/40 backdrop:backdrop-blur-[1px] open:flex',
        isDrawer
          ? 'm-0 h-dvh max-h-dvh w-full max-w-full items-stretch justify-end'
          : 'm-0 h-dvh max-h-dvh w-full max-w-full items-end justify-center sm:items-center',
      )}
    >
      <div
        className={cn(
          'flex w-full flex-col overflow-hidden bg-surface text-left',
          isDrawer
            ? cn('h-full border-l border-border', DRAWER_SIZES[size])
            : cn(
                'max-h-[92dvh] rounded-t-2xl border border-border sm:m-4 sm:rounded-card sm:shadow-floating',
                SIZES[size],
              ),
          className,
        )}
      >
        <header className="flex items-start justify-between gap-4 px-5 pt-5 pb-3 sm:px-6">
          <div className="min-w-0">
            <h2 id={titleId} className="text-lg font-semibold text-brand-950">
              {title}
            </h2>
            {description && (
              <p id={descId} className="mt-1 text-sm text-ink-500">
                {description}
              </p>
            )}
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            disabled={!dismissible}
            aria-label="Close"
            className="-mt-1 -mr-2"
          >
            <X className="size-4" />
          </Button>
        </header>
        <div className="min-h-0 flex-1 scrollbar-thin overflow-y-auto px-5 pb-5 sm:px-6">
          {children}
        </div>
        {footer && (
          <footer className="flex flex-col-reverse gap-2 border-t border-border bg-surface-muted px-5 py-3 safe-bottom sm:flex-row sm:justify-end sm:px-6">
            {footer}
          </footer>
        )}
      </div>
    </dialog>
  );
}
