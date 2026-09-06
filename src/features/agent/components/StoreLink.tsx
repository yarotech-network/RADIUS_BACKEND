import { useState, type FormEvent } from 'react';
import { Link2, Store } from 'lucide-react';
import { Button, FormField, Input } from '@/components/ui';
import { Alert } from '@/components/feedback';
import { storefrontApi } from '@/features/storefront/api';
import { isApiError } from '@/services/api/errors';
import { normaliseStoreSlug, useStoreSlug } from '../storeSlug';

/**
 * Lets the agent connect the portal to their operator's storefront (gap #1 — the API does not
 * expose the tenant slug to agents). The slug is verified against `public/tenants/<slug>/`.
 */
export function StoreLinkForm({
  onLinked,
  compact = false,
}: {
  onLinked?: (slug: string) => void;
  compact?: boolean;
}) {
  const [, setSlug] = useStoreSlug();
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const slug = normaliseStoreSlug(value);
    if (!slug) {
      setError('Enter the storefront address, e.g. wuse-hotspot or https://…/s/wuse-hotspot');
      return;
    }
    setBusy(true);
    try {
      const tenant = await storefrontApi.tenant(slug);
      setSlug(tenant.slug);
      onLinked?.(tenant.slug);
    } catch (e) {
      setError(
        isApiError(e) && e.status === 404
          ? 'No storefront found at that address. Ask your operator for the exact link.'
          : 'Could not check the storefront right now. Please try again.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(e) => void submit(e)}
      noValidate
      className={
        compact
          ? 'flex flex-col gap-3'
          : 'flex flex-col gap-4 rounded-card border border-border bg-surface p-5'
      }
      aria-label="Connect storefront"
    >
      {!compact && (
        <div className="flex items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-700">
            <Store className="size-5" aria-hidden />
          </span>
          <div>
            <h2 className="text-base font-semibold text-brand-950">
              Connect your operator's storefront
            </h2>
            <p className="mt-1 text-sm text-ink-600">
              Plans and prices come from the storefront you sell for. Paste its link once — it is
              remembered on this device.
            </p>
          </div>
        </div>
      )}
      {error && <Alert tone="danger">{error}</Alert>}
      <FormField
        label="Storefront link or name"
        required
        hint="It looks like /s/your-operator in the address bar."
      >
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="https://…/s/wuse-hotspot"
          autoCapitalize="none"
          spellCheck={false}
          inputMode="url"
        />
      </FormField>
      <div className="flex justify-end">
        <Button type="submit" loading={busy} leadingIcon={<Link2 className="size-4" aria-hidden />}>
          Connect
        </Button>
      </div>
    </form>
  );
}
