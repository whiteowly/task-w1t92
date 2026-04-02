from django.urls import include, path
from rest_framework.routers import DefaultRouter

from logistics.views import (
    GroupLeaderOnboardingViewSet,
    LocationViewSet,
    PickupPointBusinessHourViewSet,
    PickupPointClosureViewSet,
    PickupPointViewSet,
    WarehouseViewSet,
    ZoneViewSet,
)

router = DefaultRouter()
router.register("warehouses", WarehouseViewSet, basename="warehouse")
router.register("zones", ZoneViewSet, basename="zone")
router.register("locations", LocationViewSet, basename="location")
router.register("pickup-points", PickupPointViewSet, basename="pickup-point")
router.register(
    "pickup-point-business-hours",
    PickupPointBusinessHourViewSet,
    basename="pickup-point-business-hour",
)
router.register(
    "pickup-point-closures",
    PickupPointClosureViewSet,
    basename="pickup-point-closure",
)
router.register(
    "group-leader-onboardings",
    GroupLeaderOnboardingViewSet,
    basename="group-leader-onboarding",
)

urlpatterns = [
    path("", include(router.urls)),
]
