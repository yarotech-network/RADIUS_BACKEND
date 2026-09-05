import json
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse


class ApiErrorEnvelopeMiddleware:
    """Add a stable problem envelope while retaining existing v1 error fields."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/api/") or response.status_code < 400 or response.streaming:
            return response
        try:
            data = json.loads(response.content)
        except (ValueError, UnicodeDecodeError):
            data = {"detail": "The request could not be completed."}
            replacement = JsonResponse(data, status=response.status_code)
            for header in ("WWW-Authenticate", "Retry-After"):
                if header in response:
                    replacement[header] = response[header]
            response = replacement
        if not isinstance(data, dict):
            data = {"detail": data}
        fields = {k: v for k, v in data.items() if isinstance(v, list)}
        message = data.get("detail") or data.get("error") or "Check the submitted fields."
        if not isinstance(message, str):
            message = "The request could not be completed."
        data["problem"] = {"code": f"http_{response.status_code}", "message": message, "fields": fields}
        response.content = json.dumps(data, cls=DjangoJSONEncoder)
        response["Content-Type"] = "application/json"
        response["Content-Length"] = len(response.content)
        return response
