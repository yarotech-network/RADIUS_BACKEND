import { useEffect, useState } from 'react';
import { Alert } from '@/components/feedback/Alert';

/** Counts down a 429 Retry-After so the user knows when to try again. */
export function ThrottleNotice({ seconds, onDone }: { seconds: number; onDone?: () => void }) {
  const [deadline] = useState(() => Date.now() + seconds * 1000);
  const [now, setNow] = useState(() => Date.now());
  const left = Math.max(0, Math.ceil((deadline - now) / 1000));
  useEffect(() => {
    if (left <= 0) {
      onDone?.();
      return;
    }
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [left, onDone]);
  return (
    <Alert tone="warning" title="Too many attempts">
      {left > 0
        ? `You can try again in ${left} second${left === 1 ? '' : 's'}.`
        : 'You can try again now.'}
    </Alert>
  );
}
