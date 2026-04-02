from django.urls import include, path
from rest_framework.routers import DefaultRouter

from finance.views import (
    CommissionRuleViewSet,
    LedgerEntryViewSet,
    SettlementViewSet,
    WithdrawalBlacklistViewSet,
    WithdrawalRequestViewSet,
)

router = DefaultRouter()
router.register("commission-rules", CommissionRuleViewSet, basename="commission-rule")
router.register("ledger-entries", LedgerEntryViewSet, basename="ledger-entry")
router.register("settlements", SettlementViewSet, basename="settlement")
router.register(
    "withdrawal-blacklist", WithdrawalBlacklistViewSet, basename="withdrawal-blacklist"
)
router.register(
    "withdrawal-requests", WithdrawalRequestViewSet, basename="withdrawal-request"
)

urlpatterns = [
    path("", include(router.urls)),
]
