import { useCallback, useRef, useState } from 'react';
import { useToast } from '@/components/feedback';
import { printHtml } from '@/lib/utilities/download';
import { usePrincipal } from '@/app/auth/useAuth';
import { workspaceName } from '@/services/auth/principal';
import { buildPrintSheet, fetchCredentials, type BulkPrintProgress } from '../printing';

/**
 * Prints one or many vouchers via the server's print endpoint (the only credential source).
 * Sequential fetch → single print sheet; progress is exposed for the UI.
 */
export function usePrintVouchers() {
  const toast = useToast();
  const principal = usePrincipal();
  const [progress, setProgress] = useState<BulkPrintProgress | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const print = useCallback(
    async (ids: readonly number[]) => {
      if (ids.length === 0) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setProgress({ done: 0, total: ids.length });
      try {
        const { ok, failed } = await fetchCredentials(ids, setProgress, controller.signal);
        if (controller.signal.aborted) return;
        if (ok.length === 0) {
          toast.error(
            'Nothing to print',
            failed.length ? 'The credential pages could not be loaded.' : undefined,
          );
          return;
        }
        printHtml(
          buildPrintSheet(ok, {
            tenantName: workspaceName(principal) ?? 'Wi-Fi voucher',
            footnote: 'Connect to the hotspot and enter these details on the login page.',
          }),
        );
        if (failed.length)
          toast.error(
            `${failed.length} of ${ids.length} vouchers skipped`,
            'They could not be loaded — try printing them individually.',
          );
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
          setProgress(null);
        }
      }
    },
    [principal, toast],
  );

  const cancel = useCallback(() => abortRef.current?.abort(), []);

  return { print, cancel, progress, printing: progress !== null };
}
