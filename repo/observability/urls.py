from django.urls import include, path
from rest_framework.routers import DefaultRouter

from observability.views import (
    AuditLogViewSet,
    MetricsSnapshotViewSet,
    ReportExportViewSet,
)

router = DefaultRouter()
router.register("audit-logs", AuditLogViewSet, basename="audit-log")
router.register(
    "metrics-snapshots", MetricsSnapshotViewSet, basename="metrics-snapshot"
)
router.register("report-exports", ReportExportViewSet, basename="report-export")

urlpatterns = [
    path("", include(router.urls)),
]
