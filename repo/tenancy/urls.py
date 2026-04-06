from django.urls import include, path
from rest_framework.routers import DefaultRouter

from tenancy.views import (
    CurrentOrganizationView,
    OrganizationViewSet,
    TenantConfigCurrentView,
    TenantConfigRollbackView,
    TenantConfigVersionListView,
)

router = DefaultRouter()
router.register("organizations", OrganizationViewSet, basename="organization")

urlpatterns = [
    path(
        "organizations/current/",
        CurrentOrganizationView.as_view(),
        name="current-organization",
    ),
    path("config/", TenantConfigCurrentView.as_view(), name="tenant-config-current"),
    path(
        "config/versions/",
        TenantConfigVersionListView.as_view(),
        name="tenant-config-versions",
    ),
    path(
        "config/versions/<int:version_id>/rollback/",
        TenantConfigRollbackView.as_view(),
        name="tenant-config-rollback",
    ),
    path("", include(router.urls)),
]
