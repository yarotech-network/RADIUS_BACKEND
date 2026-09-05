from django.db import transaction
from .api import audit
from .commands import idempotent


class AuditedCrudMixin:
    """Audit authorized CRUD in the same database transaction as the mutation."""

    @idempotent
    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            response = super().create(request, *args, **kwargs)
            instance = self.get_queryset().get(pk=response.data["id"])
            audit(request, f"{instance._meta.model_name}.created", instance)
            return response

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            response = super().update(request, *args, **kwargs)
            instance = self.get_object()
            audit(request, f"{instance._meta.model_name}.updated", instance)
            return response

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            instance = self.get_object()
            audit(request, f"{instance._meta.model_name}.deleted", instance)
            return super().destroy(request, *args, **kwargs)
