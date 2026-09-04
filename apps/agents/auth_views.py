from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate, get_user_model
from apps.core.permissions import IsAgent
from .models import AgentProfile
from .serializers import AgentLoginSerializer, AgentStatsSerializer

User = get_user_model()


class AgentLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = AgentLoginSerializer

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        user = authenticate(request=request, username=username, password=password)
        if user is not None:
            if not hasattr(user, "agent_profile"):
                return Response(
                    {"error": "Not an agent account"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if user.agent_profile.status != "active":
                return Response(
                    {"error": "Agent account is not active"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            refresh = RefreshToken.for_user(user)
            return Response({
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "agent": {
                    "id": user.agent_profile.id,
                    "username": user.username,
                    "shop_name": user.agent_profile.shop_name,
                },
            })

        return Response(
            {"error": "Invalid credentials"},
            status=status.HTTP_401_UNAUTHORIZED,
        )


class AgentDashboardView(APIView):
    permission_classes = [IsAgent]
    serializer_class = AgentStatsSerializer

    def get(self, request):
        from .services import AgentService
        stats = AgentService.get_agent_stats(request.user.agent_profile)
        return Response(stats)
