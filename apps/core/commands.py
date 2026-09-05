"""Durable duplicate suppression. Ambiguous requests stay reserved, never reexecuted."""
import hashlib
import hmac
import json
import re
from functools import wraps
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from rest_framework.response import Response
from .models import ApiCommand


def idempotent(function):
    @wraps(function)
    def wrapped(view, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        if not key:
            return function(view, request, *args, **kwargs)
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{16,128}", key):
            return Response({"error": "Idempotency-Key must contain 16 to 128 safe ASCII characters."}, status=400)
        membership = getattr(request.user, "membership", None)
        scope = f"{request.user.pk or 'public'}:{getattr(membership, 'tenant_id', request.headers.get('X-Tenant-ID', ''))}:{request.method}:{request.path}"
        scope = hashlib.sha256(scope.encode()).hexdigest()
        fingerprint = hmac.new(settings.SECRET_KEY.encode(), json.dumps(request.data, sort_keys=True, cls=DjangoJSONEncoder).encode(), hashlib.sha256).hexdigest()
        with transaction.atomic():
            command, created = ApiCommand.objects.get_or_create(scope=scope, key=key, defaults={"fingerprint": fingerprint})
            if not created:
                if command.fingerprint != fingerprint:
                    return Response({"error": "Idempotency key was used with a different payload."}, status=409)
                if command.status != "complete":
                    return Response({"error": "Command is pending or requires reconciliation.", "command_id": str(command.pk)}, status=409, headers={"Retry-After": "5"})
                return Response(command.response, status=command.status_code, headers={"Idempotency-Replayed": "true"})
        try:
            response = function(view, request, *args, **kwargs)
        except Exception as exc:
            # Persist the same sanitized DRF error; do not rerun an ambiguous
            # operation simply because its caller saw a timeout or exception.
            response = view.handle_exception(exc)
        ApiCommand.objects.filter(pk=command.pk).update(
            status="complete", response=json.loads(json.dumps(response.data, cls=DjangoJSONEncoder)),
            status_code=response.status_code, completed_at=timezone.now(),
        )
        response["Idempotency-Replayed"] = "false"
        return response
    wrapped.idempotency_supported = True
    return wrapped
