from __future__ import annotations

from collections import Counter
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from events.models import Event, EventCheckIn, EventRegistration, EventResourceDownload


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def compute_event_summary(*, organization, event_id: int | None = None) -> dict:
    registrations_qs = EventRegistration.objects.filter(organization=organization)
    checkins_qs = EventCheckIn.objects.filter(organization=organization)
    eligible_total = 0

    if event_id is not None:
        registrations_qs = registrations_qs.filter(event_id=event_id)
        checkins_qs = checkins_qs.filter(event_id=event_id)
        event = (
            Event.objects.filter(
                organization=organization,
                id=event_id,
            )
            .only("eligible_member_count_snapshot")
            .first()
        )
        eligible_total = event.eligible_member_count_snapshot if event else 0
    else:
        events = Event.objects.filter(organization=organization).only(
            "eligible_member_count_snapshot"
        )
        eligible_total = sum(event.eligible_member_count_snapshot for event in events)

    registration_count = registrations_qs.count()
    checkin_count = checkins_qs.count()

    since = timezone.now() - timedelta(days=30)
    active_checkin_members = set(
        EventCheckIn.objects.filter(
            organization=organization,
            checked_in_at__gte=since,
        ).values_list("member_id", flat=True)
    )
    active_download_members = set(
        EventResourceDownload.objects.filter(
            organization=organization,
            downloaded_at__gte=since,
        ).values_list("member_id", flat=True)
    )
    active_members = len(active_checkin_members | active_download_members)

    return {
        "eligible_members": eligible_total,
        "registrations": registration_count,
        "checked_in": checkin_count,
        "conversion_rate": _safe_rate(registration_count, eligible_total),
        "attendance_rate": _safe_rate(checkin_count, registration_count),
        "active_members_last_30_days": active_members,
    }


def compute_checkin_distribution(
    *, organization, event_id: int | None = None
) -> list[dict]:
    checkins_qs = EventCheckIn.objects.filter(organization=organization).only(
        "checked_in_at"
    )
    if event_id is not None:
        checkins_qs = checkins_qs.filter(event_id=event_id)

    org_tz = ZoneInfo(organization.timezone or "UTC")
    bucket_counts: Counter[str] = Counter()

    for checkin in checkins_qs.iterator():
        local_time = checkin.checked_in_at.astimezone(org_tz)
        bucket_minute = (local_time.minute // 15) * 15
        bucket_label = f"{local_time.hour:02d}:{bucket_minute:02d}"
        bucket_counts[bucket_label] += 1

    ordered = []
    for hour in range(24):
        for minute in (0, 15, 30, 45):
            label = f"{hour:02d}:{minute:02d}"
            ordered.append({"bucket": label, "count": bucket_counts.get(label, 0)})
    return ordered
