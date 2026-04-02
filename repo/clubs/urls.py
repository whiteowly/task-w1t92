from django.urls import include, path
from rest_framework.routers import DefaultRouter

from clubs.views import ClubViewSet, DepartmentViewSet, MembershipViewSet

router = DefaultRouter()
router.register("clubs", ClubViewSet, basename="club")
router.register("departments", DepartmentViewSet, basename="department")
router.register("memberships", MembershipViewSet, basename="membership")

urlpatterns = [
    path("", include(router.urls)),
]
