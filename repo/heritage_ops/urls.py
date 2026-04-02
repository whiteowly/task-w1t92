from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", include("common.urls")),
    path("api/v1/auth/", include("iam.urls")),
    path("api/v1/tenancy/", include("tenancy.urls")),
    path("api/v1/clubs/", include("clubs.urls")),
    path("api/v1/events/", include("events.urls")),
    path("api/v1/analytics/", include("analytics.urls")),
    path("api/v1/logistics/", include("logistics.urls")),
    path("api/v1/finance/", include("finance.urls")),
    path("api/v1/content/", include("content.urls")),
    path("api/v1/observability/", include("observability.urls")),
]
