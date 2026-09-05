from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, DatabaseError
from django.db.models.deletion import ProtectedError
from rest_framework.exceptions import ValidationError


def custom_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(getattr(exc, "message_dict", None) or exc.messages)
    if isinstance(exc, ProtectedError):
        return Response({"detail": "This resource is referenced by retained records."}, status=409)
    if isinstance(exc, IntegrityError):
        # Do not expose SQL, constraint names, or values from another tenant.
        return Response({"detail": "The request conflicts with an existing record."}, status=409)
    if isinstance(exc, DatabaseError):
        import logging
        logging.getLogger(__name__).error("api_database_unavailable", extra={"error_type": type(exc).__name__})
        return Response({"detail": "A required database service or schema is unavailable."}, status=503)
    return exception_handler(exc, context)
