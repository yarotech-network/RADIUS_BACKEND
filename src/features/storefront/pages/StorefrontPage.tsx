import { useEffect } from 'react';
import { Route, Routes, useParams } from 'react-router';
import { Wifi } from 'lucide-react';
import { ButtonLink } from '@/components/ui';
import { EmptyState, ErrorState } from '@/components/feedback';
import { NotFoundPage } from '@/app/shell/NotFoundPage';
import { isApiError } from '@/services/api/errors';
import { usePublicPlans, usePublicTenant } from '../queries';
import { PlanCard, PlanCardSkeleton } from '../components/PlanCard';
import CheckoutPage from './CheckoutPage';

/** `/s/:slug/*` — public storefront: plan catalogue → checkout. */
export default function StorefrontPage() {
  const { slug = '' } = useParams();
  const tenant = usePublicTenant(slug);

  useEffect(() => {
    if (tenant.data) document.title = `${tenant.data.name} · Buy Wi-Fi`;
  }, [tenant.data]);

  if (tenant.isError && isApiError(tenant.error) && tenant.error.status === 404) {
    return (
      <NotFoundPage
        homePath="/"
        title="This storefront does not exist"
        description="Check the link you were given — the business may have changed its address."
      />
    );
  }

  return (
    <div className="mx-auto w-full max-w-4xl">
      <Routes>
        <Route
          index
          element={
            <Catalogue
              slug={slug}
              tenantName={tenant.data?.name ?? null}
              tenantLoading={tenant.isPending}
              tenantError={tenant.isError ? tenant.error : null}
              onRetryTenant={() => void tenant.refetch()}
            />
          }
        />
        <Route
          path="checkout/:planId"
          element={<CheckoutPage slug={slug} tenantName={tenant.data?.name ?? null} />}
        />
        <Route path="*" element={<NotFoundPage homePath={`/s/${slug}`} />} />
      </Routes>
    </div>
  );
}

function Catalogue({
  slug,
  tenantName,
  tenantLoading,
  tenantError,
  onRetryTenant,
}: {
  slug: string;
  tenantName: string | null;
  tenantLoading: boolean;
  tenantError: unknown;
  onRetryTenant: () => void;
}) {
  // Plans are only requested once the storefront itself resolves (avoids a doomed second call on 404).
  const plans = usePublicPlans(
    tenantName !== null || (!tenantLoading && !tenantError) ? slug : null,
  );
  return (
    <>
      <header className="mb-6 text-center sm:text-left">
        <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-full bg-brand-50 text-brand-700 sm:mx-0">
          <Wifi className="size-6" aria-hidden />
        </div>
        {tenantLoading ? (
          <div className="mx-auto h-7 w-48 animate-pulse rounded bg-slate-200 sm:mx-0" />
        ) : (
          <h1 className="text-2xl font-semibold text-brand-950">{tenantName ?? 'Buy Wi-Fi'}</h1>
        )}
        <p className="mt-1 text-sm text-ink-500">
          Choose a plan, pay securely with Paystack, and get connected.
        </p>
      </header>
      {tenantError ? (
        <ErrorState
          error={tenantError}
          onRetry={onRetryTenant}
          title="Could not load this storefront"
        />
      ) : plans.isPending ? (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy>
          {[0, 1, 2].map((i) => (
            <li key={i}>
              <PlanCardSkeleton />
            </li>
          ))}
        </ul>
      ) : plans.isError ? (
        <ErrorState
          error={plans.error}
          onRetry={() => void plans.refetch()}
          title="Could not load plans"
        />
      ) : plans.data.results.length === 0 ? (
        <EmptyState
          icon={<Wifi className="size-6" aria-hidden />}
          title="No plans available right now"
          description="This business has not published any internet plans yet. Please check back later."
        />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {plans.data.results.map((plan) => (
            <li key={plan.id}>
              <PlanCard
                plan={plan}
                action={
                  <ButtonLink to={`/s/${slug}/checkout/${plan.id}`} block>
                    Buy
                  </ButtonLink>
                }
              />
            </li>
          ))}
        </ul>
      )}
      <p className="mt-8 text-center text-xs text-ink-400">
        Payments are processed by Paystack. Your login details are sent to you by{' '}
        {tenantName ?? 'the business'} after payment.
      </p>
    </>
  );
}
