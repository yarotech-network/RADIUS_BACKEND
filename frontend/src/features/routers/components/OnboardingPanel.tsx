import { useState } from 'react';
import { AlertTriangle, ArrowRight, Check, Pause, RotateCcw, Undo2 } from 'lucide-react';
import { Button, ConfirmDialog } from '@/components/ui';
import { Alert, useToast } from '@/components/feedback';
import { cn } from '@/lib/utilities/cn';
import { errorMessage } from '@/services/api/errors';
import type { NasDevice, OnboardingState } from '@/types/api';
import { useTransitionRouter } from '../queries';
import {
  ONBOARDING_LABELS,
  ONBOARDING_STEPS,
  isFailureState,
  nextStates,
  onboardingStepIndex,
  transitionIntent,
} from '../routerRules';

const INTENT_STYLE = {
  forward: { variant: 'primary', icon: ArrowRight, prefix: 'Mark as' },
  retry: { variant: 'primary', icon: RotateCcw, prefix: 'Retry:' },
  back: { variant: 'secondary', icon: Undo2, prefix: 'Send back to' },
  suspend: { variant: 'danger', icon: Pause, prefix: '' },
  fail: { variant: 'secondary', icon: AlertTriangle, prefix: 'Record' },
} as const;

/** Progress stepper + the transition buttons the state machine allows from the current state. */
export function OnboardingPanel({ router, canManage }: { router: NasDevice; canManage: boolean }) {
  const toast = useToast();
  const transition = useTransitionRouter();
  const [confirm, setConfirm] = useState<OnboardingState | null>(null);
  const current = router.onboarding_state;
  const index = onboardingStepIndex(current);
  const failed = isFailureState(current);
  const options = nextStates(current);

  async function apply(to: OnboardingState) {
    try {
      await transition.mutateAsync({ id: router.id, payload: { to_state: to } });
      toast.success(`Router is now “${ONBOARDING_LABELS[to]}”`);
    } catch (error) {
      toast.error('Transition rejected', errorMessage(error));
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <ol className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6" aria-label="Onboarding progress">
        {ONBOARDING_STEPS.map((step, i) => {
          const state =
            current === 'suspended'
              ? 'todo'
              : i < index
                ? 'done'
                : i === index
                  ? failed
                    ? 'failed'
                    : 'current'
                  : 'todo';
          return (
            <li
              key={step.state}
              className={cn(
                'rounded-card border p-3',
                state === 'current' && 'border-brand-600 bg-brand-50',
                state === 'failed' && 'border-danger-600 bg-danger-50',
                state === 'done' && 'border-border bg-surface',
                state === 'todo' && 'border-dashed border-border',
              )}
            >
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    'grid h-5 w-5 shrink-0 place-items-center rounded-full text-[11px] font-semibold',
                    state === 'done' && 'bg-brand-600 text-white',
                    state === 'current' && 'border border-brand-600 text-brand-700',
                    state === 'failed' && 'bg-danger-600 text-white',
                    state === 'todo' && 'border border-border-strong text-ink-400',
                  )}
                  aria-hidden
                >
                  {state === 'done' ? (
                    <Check className="h-3 w-3" />
                  ) : state === 'failed' ? (
                    '!'
                  ) : (
                    i + 1
                  )}
                </span>
                <span className="text-sm font-medium text-ink-900">{step.title}</span>
              </div>
              <p className="mt-1 text-xs text-ink-500">
                {state === 'failed' ? ONBOARDING_LABELS[current] : step.hint}
              </p>
            </li>
          );
        })}
      </ol>

      {current === 'suspended' && (
        <Alert tone="warning" title="Router suspended">
          It no longer serves customers. Re-activate it, or send it back to the start of onboarding.
        </Alert>
      )}
      {failed && (
        <Alert tone="danger" title={ONBOARDING_LABELS[current]}>
          Fix the underlying problem (see Checks), then retry the step.
        </Alert>
      )}

      {canManage && options.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-ink-900">Next step</h3>
          <p className="mb-3 text-xs text-ink-500">
            Only transitions allowed by the onboarding workflow are shown.
          </p>
          <div className="flex flex-wrap gap-2">
            {options.map((to) => {
              const intent = transitionIntent(current, to);
              const style = INTENT_STYLE[intent];
              const Icon = style.icon;
              return (
                <Button
                  key={to}
                  variant={style.variant}
                  leadingIcon={<Icon className="h-4 w-4" aria-hidden />}
                  onClick={() =>
                    intent === 'suspend' || intent === 'back' ? setConfirm(to) : void apply(to)
                  }
                  loading={transition.isPending && transition.variables?.payload.to_state === to}
                  disabled={transition.isPending}
                >
                  {style.prefix
                    ? `${style.prefix} ${ONBOARDING_LABELS[to]}`
                    : ONBOARDING_LABELS[to]}
                </Button>
              );
            })}
          </div>
        </div>
      )}
      {!canManage && (
        <p className="text-xs text-ink-500">Only managers can move a router through onboarding.</p>
      )}

      <ConfirmDialog
        open={confirm !== null}
        onClose={() => setConfirm(null)}
        tone="danger"
        title={
          confirm
            ? `${transitionIntent(current, confirm) === 'suspend' ? 'Suspend' : 'Send back'} ${router.name}?`
            : ''
        }
        description={
          confirm === 'suspended'
            ? 'Customers on this router will no longer be able to log in until it is re-activated.'
            : 'Onboarding starts over from the beginning; existing configuration is kept.'
        }
        confirmLabel={confirm === 'suspended' ? 'Suspend router' : 'Send back'}
        onConfirm={async () => {
          if (!confirm) return;
          await transition.mutateAsync({ id: router.id, payload: { to_state: confirm } });
          toast.success(`Router is now “${ONBOARDING_LABELS[confirm]}”`);
        }}
      />
    </div>
  );
}
