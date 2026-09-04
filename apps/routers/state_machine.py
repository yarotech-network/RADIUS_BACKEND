from .models import NASDevice, RouterAuditEvent
from django.db import transaction
import uuid


class RouterStateMachine:
    """Manage NASDevice onboarding state transitions."""

    VALID_TRANSITIONS = {
        "pending": ["reviewed"],
        "reviewed": ["approved", "pending"],
        "approved": ["waiting_for_vpn"],
        "waiting_for_vpn": ["vpn_failed", "testing_radius"],
        "vpn_failed": ["waiting_for_vpn", "suspended"],
        "testing_radius": ["radius_failed", "accounting_failed", "active"],
        "radius_failed": ["testing_radius", "suspended"],
        "accounting_failed": ["testing_radius", "suspended"],
        "active": ["suspended"],
        "suspended": ["active", "pending"],
    }

    @classmethod
    def can_transition(cls, from_state, to_state):
        return to_state in cls.VALID_TRANSITIONS.get(from_state, [])

    @classmethod
    @transaction.atomic
    def transition(cls, router, to_state, action="state_change", details=None):
        router = NASDevice.objects.select_for_update().get(pk=router.pk)
        if not cls.can_transition(router.onboarding_state, to_state):
            raise ValueError(
                f"Invalid transition: {router.onboarding_state} -> {to_state}"
            )

        from_state = router.onboarding_state
        correlation_id = uuid.uuid4()

        router.onboarding_state = to_state
        router.save(update_fields=["onboarding_state", "updated_at"])

        RouterAuditEvent.objects.create(
            router=router,
            action=action,
            from_state=from_state,
            to_state=to_state,
            correlation_id=correlation_id,
            details=details or {},
        )

        return correlation_id
