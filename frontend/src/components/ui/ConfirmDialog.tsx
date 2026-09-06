import { useState, type ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Dialog } from './Dialog';
import { Button } from './Button';
import { Input } from './Input';
import { FormField } from './FormField';
import { Alert } from '@/components/feedback/Alert';
import { errorMessage } from '@/services/api/errors';

export interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => Promise<unknown> | void;
  title: ReactNode;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: 'default' | 'danger';
  /** Require the user to type this phrase before confirming (destructive actions). */
  typeToConfirm?: string;
  children?: ReactNode;
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'default',
  typeToConfirm,
  children,
}: ConfirmDialogProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typed, setTyped] = useState('');
  const canConfirm = !typeToConfirm || typed.trim() === typeToConfirm;

  const close = () => {
    if (busy) return;
    setError(null);
    setTyped('');
    onClose();
  };

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      setTyped('');
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      title={
        <span className="flex items-center gap-2">
          {tone === 'danger' && <AlertTriangle className="size-5 text-danger-600" aria-hidden />}
          {title}
        </span>
      }
      description={description}
      size="sm"
      dismissible={!busy}
      footer={
        <>
          <Button variant="secondary" onClick={close} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button
            variant={tone === 'danger' ? 'danger' : 'primary'}
            onClick={confirm}
            loading={busy}
            disabled={!canConfirm}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
      {typeToConfirm && (
        <FormField
          label={
            <>
              Type <span className="font-mono font-semibold">{typeToConfirm}</span> to continue
            </>
          }
          className="mt-2"
        >
          <Input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </FormField>
      )}
      {error && (
        <Alert tone="danger" className="mt-3">
          {error}
        </Alert>
      )}
    </Dialog>
  );
}
