from django.urls import path

from tenancy.views import (
    CurrentOrganizationView,
    TenantConfigCurrentView,
    TenantConfigRollbackView,
    TenantConfigVersionListView,
)

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
]
