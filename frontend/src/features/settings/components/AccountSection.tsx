import { CopyButton, DescriptionList } from '@/components/ui';
import { useAuth } from '@/app/auth/useAuth';
import { ChangePasswordForm } from './ChangePasswordForm';
import { SettingsCard } from './SettingsCard';

/** Signed-in user's identity (with the numeric ID owners need to add them to a team) and password change. */
export function AccountSection() {
  const { principal } = useAuth();
  const user = principal?.user;
  const roleLabel = principal?.kind === 'member' ? principal.role : (user?.role ?? '');
  return (
    <>
      <SettingsCard
        id="account"
        title="Your account"
        description="Team owners add people by user ID — share yours if you need access to another workspace."
      >
        {user && (
          <DescriptionList
            columns={2}
            items={[
              {
                label: 'User ID',
                value: (
                  <span className="inline-flex items-center gap-1 font-mono text-[13px]">
                    {user.id}
                    <CopyButton value={String(user.id)} label="Copy user ID" />
                  </span>
                ),
              },
              {
                label: 'Role',
                value: <span className="capitalize">{roleLabel.replace('_', ' ')}</span>,
              },
              { label: 'Username', value: user.username, mono: true },
              { label: 'Email', value: user.email },
              {
                label: 'Name',
                value: [user.first_name, user.last_name].filter(Boolean).join(' ') || null,
              },
              { label: 'Phone', value: user.phone || null, mono: true },
            ]}
          />
        )}
      </SettingsCard>
      <SettingsCard
        id="password"
        title="Password"
        description="Use at least 8 characters that are not all digits. You stay signed in here; every other device and browser is signed out."
      >
        <ChangePasswordForm />
      </SettingsCard>
    </>
  );
}
