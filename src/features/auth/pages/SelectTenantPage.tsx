import { useEffect } from 'react';
import { Navigate, useNavigate } from 'react-router';
import { Building2, ChevronRight } from 'lucide-react';
import { useAuth } from '@/app/auth/useAuth';
import { AuthCard } from '@/app/shell/AuthCard';
import { Alert } from '@/components/feedback/Alert';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { tenantLabel, useAssignedTenantNames } from '@/app/shell/useAssignedTenantNames';
import { homePathFor } from '@/services/auth/principal';
import { humanise } from '@/lib/formatting/units';

export default function SelectTenantPage() {
  const { principal, selectTenant, signOut } = useAuth();
  const navigate = useNavigate();
  const ids =
    principal?.kind === 'platform_staff' ? principal.assignments.map((a) => a.tenant) : [];
  const names = useAssignedTenantNames(ids);

  useEffect(() => {
    document.title = 'Choose tenant · Yarotech RADIUS';
  }, []);

  if (!principal) return <Navigate to="/login" replace />;
  if (principal.kind !== 'platform_staff') return <Navigate to={homePathFor(principal)} replace />;

  const choose = (tenantId: number) => {
    selectTenant(tenantId);
    // The workspace overview — homePathFor(principal) would still say /select-tenant
    // because the context update is async at this point.
    navigate('/dashboard', { replace: true });
  };

  return (
    <AuthCard
      title="Choose a tenant"
      description="You have staff access to the tenants below. You can switch at any time from the top bar."
      wide
    >
      {principal.assignments.length === 0 ? (
        <div className="space-y-4">
          <Alert tone="warning" title="No active assignments">
            Your account has no active tenant assignments. Ask a platform administrator to assign
            you, or accept a pending invitation link.
          </Alert>
          <Button variant="secondary" onClick={() => void signOut()}>
            Sign out
          </Button>
        </div>
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-card border border-border">
          {principal.assignments.map((assignment) => (
            <li key={assignment.id}>
              <button
                type="button"
                onClick={() => choose(assignment.tenant)}
                className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-brand-50/60 focus-visible:outline-brand-600"
              >
                <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-700">
                  <Building2 className="size-4" aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-ink-900">
                    {tenantLabel(names.data, assignment.tenant)}
                  </span>
                  <span className="mt-1 flex flex-wrap gap-1">
                    {assignment.services.map((s) => (
                      <Badge key={s} tone="outline" size="sm">
                        {humanise(s)}
                      </Badge>
                    ))}
                  </span>
                </span>
                <ChevronRight className="size-4 shrink-0 text-ink-400" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
    </AuthCard>
  );
}
