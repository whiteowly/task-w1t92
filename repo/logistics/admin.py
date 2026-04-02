from django.contrib import admin

from logistics.models import (
    GroupLeaderOnboarding,
    Location,
    PickupPoint,
    PickupPointBusinessHour,
    PickupPointClosure,
    Warehouse,
    Zone,
)

admin.site.register(Warehouse)
admin.site.register(Zone)
admin.site.register(Location)
admin.site.register(PickupPoint)
admin.site.register(PickupPointBusinessHour)
admin.site.register(PickupPointClosure)
admin.site.register(GroupLeaderOnboarding)
