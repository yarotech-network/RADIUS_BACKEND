import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { copyToClipboard } from '@/lib/utilities/clipboard';
import { Button, type ButtonProps } from './Button';

export function CopyButton({
  value,
  label = 'Copy',
  size = 'sm',
  variant = 'ghost',
  ...rest
}: { value: string; label?: string } & Omit<ButtonProps, 'onClick' | 'children'>) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      size={size}
      variant={variant}
      aria-label={copied ? 'Copied' : label}
      onClick={async () => {
        const ok = await copyToClipboard(value);
        if (ok) {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        }
      }}
      leadingIcon={copied ? <Check className="text-success-600" /> : <Copy />}
      {...rest}
    >
      {size === 'icon' ? null : copied ? 'Copied' : label}
    </Button>
  );
}
