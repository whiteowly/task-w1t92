from django.urls import include, path
from rest_framework.routers import DefaultRouter

from events.views import (
    EventAttendanceReconciliationViewSet,
    EventCheckInViewSet,
    EventRegistrationViewSet,
    EventResourceDownloadViewSet,
    EventViewSet,
)

router = DefaultRouter()
router.register("events", EventViewSet, basename="event")
router.register(
    "registrations", EventRegistrationViewSet, basename="event-registration"
)
router.register("checkins", EventCheckInViewSet, basename="event-checkin")
router.register(
    "reconciliations",
    EventAttendanceReconciliationViewSet,
    basename="event-reconciliation",
)
router.register(
    "resource-downloads",
    EventResourceDownloadViewSet,
    basename="event-resource-download",
)

urlpatterns = [
    path("", include(router.urls)),
]
