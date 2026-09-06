import { Skeleton } from '@/components/ui';
import { QueryBoundary } from '@/components/feedback';
import { usePrincipal } from '@/app/auth/useAuth';
import { can } from '@/services/auth/principal';
import { useTenantProfile } from '../queries';
import { SettingsCard } from '../components/SettingsCard';
import { TenantProfileForm } from '../components/TenantProfileForm';
import { AccountSection } from '../components/AccountSection';

export default function GeneralSettingsPage() {
  const principal = usePrincipal();
  const canEdit = can(principal, 'settings.profile');
  const profile = useTenantProfile(canEdit);
  return (
    <div>
      {canEdit && (
        <SettingsCard
          id="business"
          title="Business profile"
          description="The name and contact details customers see on your storefront, vouchers and receipts."
        >
          <QueryBoundary
            query={profile}
            compact
            errorTitle="Profile could not be loaded"
            skeleton={<Skeleton className="h-64 w-full" />}
          >
            {(data) => <TenantProfileForm profile={data} />}
          </QueryBoundary>
        </SettingsCard>
      )}
      <AccountSection />
    </div>
  );
}
