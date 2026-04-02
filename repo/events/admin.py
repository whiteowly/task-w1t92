from django.contrib import admin

from events.models import (
    Event,
    EventAttendanceReconciliation,
    EventCheckIn,
    EventRegistration,
    EventResourceDownload,
)

admin.site.register(Event)
admin.site.register(EventRegistration)
admin.site.register(EventCheckIn)
admin.site.register(EventAttendanceReconciliation)
admin.site.register(EventResourceDownload)
