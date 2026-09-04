class TenantMiddleware:
    """Attach tenant to request based on authenticated user's membership."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        if hasattr(request, "user") and request.user.is_authenticated:
            if hasattr(request.user, "membership"):
                request.tenant = request.user.membership.tenant
        response = self.get_response(request)
        return response
