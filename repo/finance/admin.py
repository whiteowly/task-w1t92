from django.contrib import admin

from finance.models import (
    CommissionRule,
    LedgerEntry,
    Settlement,
    WithdrawalBlacklist,
    WithdrawalRequest,
)

admin.site.register(CommissionRule)
admin.site.register(LedgerEntry)
admin.site.register(Settlement)
admin.site.register(WithdrawalRequest)
admin.site.register(WithdrawalBlacklist)
