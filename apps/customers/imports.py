import csv
import hashlib
import io
from django.core import signing
from rest_framework.exceptions import ValidationError
from .serializers import CustomerSerializer

SALT = "customer-import-preview-v1"


def fingerprint(request, tenant, text):
    return {"tenant": tenant.pk, "actor": request.user.pk, "digest": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def validate_token(request, tenant, text, token):
    try:
        payload = signing.loads(token, salt=SALT, max_age=900)
    except (signing.BadSignature, TypeError):
        raise ValidationError({"preview_token": "Preview expired or invalid. Preview the CSV again."})
    if payload != fingerprint(request, tenant, text):
        raise ValidationError({"preview_token": "CSV or workspace changed. Preview again."})


def parse_rows(text, tenant):
    allowed = {"reference", "name", "email", "phone", "address", "notes"}
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
        headers = reader.fieldnames or []
        if not {"reference", "name"}.issubset(headers) or len(headers) != len(set(headers)) or set(headers) - allowed:
            raise ValidationError({"csv": "Use unique reference,name headers plus optional email,phone,address,notes."})
        rows, errors, seen = [], [], set()
        for index, row in enumerate(reader, start=2):
            if index > 201:
                raise ValidationError({"csv": "Import at most 200 customers at a time."})
            if None in row or any(value is None for value in row.values()):
                errors.append(f"Row {index}: column count does not match the header.")
                continue
            serializer = CustomerSerializer(data=row, context={"tenant": tenant})
            if not serializer.is_valid():
                for field, messages in serializer.errors.items():
                    errors.append(f"Row {index}, {field}: {' '.join(str(m) for m in messages)}")
                continue
            value = serializer.validated_data
            if value["reference"] in seen:
                errors.append(f"Row {index}: duplicate reference within this file.")
            seen.add(value["reference"])
            rows.append(value)
        if errors:
            raise ValidationError({"csv": errors})
        if not rows:
            raise ValidationError({"csv": "Add at least one customer row."})
        return rows
    except csv.Error:
        raise ValidationError({"csv": "Invalid CSV. Check quoting and column sizes."})
