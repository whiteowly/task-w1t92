from django.urls import include, path
from rest_framework.routers import DefaultRouter

from content.views import (
    ContentAssetViewSet,
    ContentChapterACLViewSet,
    ContentChapterViewSet,
    ContentDownloadTokenViewSet,
    ContentEntitlementViewSet,
    ContentRedeemCodeViewSet,
    SecuredContentDownloadView,
)

router = DefaultRouter()
router.register("assets", ContentAssetViewSet, basename="content-asset")
router.register("chapters", ContentChapterViewSet, basename="content-chapter")
router.register("chapter-acl", ContentChapterACLViewSet, basename="content-chapter-acl")
router.register(
    "entitlements", ContentEntitlementViewSet, basename="content-entitlement"
)
router.register(
    "redeem-codes", ContentRedeemCodeViewSet, basename="content-redeem-code"
)
router.register(
    "download-tokens", ContentDownloadTokenViewSet, basename="content-download-token"
)

urlpatterns = [
    path(
        "secured-download/<str:token>/",
        SecuredContentDownloadView.as_view(),
        name="content-secured-download",
    ),
    path("", include(router.urls)),
]
