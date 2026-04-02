from django.contrib import admin

from clubs.models import (
    Club,
    Department,
    Membership,
    MembershipStatusLog,
    MembershipTransferLog,
)

admin.site.register(Club)
admin.site.register(Department)
admin.site.register(Membership)
admin.site.register(MembershipStatusLog)
admin.site.register(MembershipTransferLog)
