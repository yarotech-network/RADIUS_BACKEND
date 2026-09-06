import { useEffect } from 'react';
import { ShieldOff } from 'lucide-react';
import { useAuth } from '@/app/auth/useAuth';
import { AuthCard } from '@/app/shell/AuthCard';
import { EmptyState } from '@/components/feedback/EmptyState';
import { Button } from '@/components/ui/Button';
import { CopyButton } from '@/components/ui/CopyButton';

/** Signed-in user with no membership, agent profile or staff assignment. */
export default function NoAccessPage() {
  const { principal, signOut } = useAuth();
  useEffect(() => {
    document.title = 'No access · Yarotech RADIUS';
  }, []);
  return (
    <AuthCard title="Nothing to show yet">
      <EmptyState
        icon={<ShieldOff />}
        title="Your account is not linked to a workspace"
        description="Ask the owner of the business to add you as a team member, or a platform administrator to assign you. They will need your user ID."
        compact
        action={
          <>
            {principal && (
              <CopyButton
                value={String(principal.user.id)}
                label={`Copy user ID ${principal.user.id}`}
                variant="secondary"
              />
            )}
            <Button variant="ghost" onClick={() => void signOut()}>
              Sign out
            </Button>
          </>
        }
      />
    </AuthCard>
  );
}
