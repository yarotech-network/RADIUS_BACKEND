import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react';
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react';
import { cn } from '@/lib/utilities/cn';
import { ToastContext, type ToastApi, type ToastOptions } from './toastContext';

interface ToastRecord extends ToastOptions {
  id: number;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);
  const counter = useRef(0);

  const dismiss = useCallback(
    (id: number) => setToasts((list) => list.filter((t) => t.id !== id)),
    [],
  );

  const toast = useCallback(
    (options: ToastOptions) => {
      const id = ++counter.current;
      const record: ToastRecord = {
        tone: 'info',
        durationMs: options.tone === 'error' ? 7000 : 4000,
        ...options,
        id,
      };
      setToasts((list) => [...list.slice(-4), record]);
      if (record.durationMs && record.durationMs > 0)
        window.setTimeout(() => dismiss(id), record.durationMs);
    },
    [dismiss],
  );

  const api = useMemo<ToastApi>(
    () => ({
      toast,
      success: (title, description) =>
        toast({ title, tone: 'success', ...(description ? { description } : {}) }),
      error: (title, description) =>
        toast({ title, tone: 'error', ...(description ? { description } : {}) }),
      info: (title, description) =>
        toast({ title, tone: 'info', ...(description ? { description } : {}) }),
    }),
    [toast],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4 safe-bottom sm:items-end"
      >
        {toasts.map((t) => {
          const Icon =
            t.tone === 'success' ? CheckCircle2 : t.tone === 'error' ? AlertCircle : Info;
          return (
            <div
              key={t.id}
              role={t.tone === 'error' ? 'alert' : 'status'}
              className={cn(
                'pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-control bg-brand-950 px-4 py-3 text-sm text-white shadow-floating',
              )}
            >
              <Icon
                className={cn(
                  'mt-0.5 size-4 shrink-0',
                  t.tone === 'success' && 'text-success-600',
                  t.tone === 'error' && 'text-danger-600',
                  t.tone === 'info' && 'text-brand-300',
                )}
                aria-hidden
              />
              <div className="min-w-0 flex-1">
                <p className="font-medium">{t.title}</p>
                {t.description && (
                  <p className="mt-0.5 text-xs leading-relaxed text-brand-200">{t.description}</p>
                )}
                {t.action && (
                  <button
                    type="button"
                    onClick={() => {
                      t.action?.onClick();
                      dismiss(t.id);
                    }}
                    className="mt-1.5 text-xs font-medium text-brand-300 underline-offset-4 hover:underline"
                  >
                    {t.action.label}
                  </button>
                )}
              </div>
              <button
                type="button"
                aria-label="Dismiss"
                onClick={() => dismiss(t.id)}
                className="-mr-1 rounded p-1 text-brand-300 hover:text-white"
              >
                <X className="size-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
