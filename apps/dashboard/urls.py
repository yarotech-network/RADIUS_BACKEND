from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/stats/", views.DashboardStatsView.as_view(), name="dashboard-stats"),
    path("dashboard/live-users/", views.LiveUsersView.as_view(), name="live-users"),
    path(
        "dashboard/live-users/<int:session_id>/disconnect/",
        views.DisconnectSessionView.as_view(),
        name="disconnect-session",
    ),
]
