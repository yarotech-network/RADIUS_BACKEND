from rest_framework_simplejwt.authentication import JWTAuthentication
from .access import enforce_request_access


class SubscriptionJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result:
            enforce_request_access(request, result[0])
        return result
