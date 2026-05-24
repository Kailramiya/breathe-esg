from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import DashboardView, IngestView, JobViewSet, RecordViewSet, MeView

router = DefaultRouter()
router.register(r"jobs", JobViewSet, basename="jobs")
router.register(r"records", RecordViewSet, basename="records")

urlpatterns = [
    path("auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("ingest/<str:source_type>/", IngestView.as_view(), name="ingest"),
    path("", include(router.urls)),
]
