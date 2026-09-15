from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .access import user_access


class SubscriptionAccessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(user_access(request, request.user), headers={'Cache-Control':'private, no-store'})
