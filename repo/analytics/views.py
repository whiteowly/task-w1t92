from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.services import compute_checkin_distribution, compute_event_summary
from common.constants import RoleCode
from common.exceptions import DomainAPIException


ANALYTICS_ALLOWED_ROLES = {
    RoleCode.ADMINISTRATOR.value,
    RoleCode.CLUB_MANAGER.value,
    RoleCode.GROUP_LEADER.value,
}


class EventAnalyticsSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        role_codes = set(getattr(request, "role_codes", []))
        if role_codes.isdisjoint(ANALYTICS_ALLOWED_ROLES):
            raise DomainAPIException(
                code="analytics.forbidden",
                message="Insufficient role to view analytics.",
                status_code=403,
            )

        event_id_value = request.query_params.get("event_id")
        try:
            event_id = int(event_id_value) if event_id_value else None
        except ValueError as exc:
            raise DomainAPIException(
                code="analytics.invalid_event_id",
                message="event_id must be an integer.",
            ) from exc
        payload = compute_event_summary(
            organization=request.organization, event_id=event_id
        )
        payload["event_id"] = event_id
        return Response(payload)


class EventCheckInDistributionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        role_codes = set(getattr(request, "role_codes", []))
        if role_codes.isdisjoint(ANALYTICS_ALLOWED_ROLES):
            raise DomainAPIException(
                code="analytics.forbidden",
                message="Insufficient role to view analytics.",
                status_code=403,
            )

        event_id_value = request.query_params.get("event_id")
        try:
            event_id = int(event_id_value) if event_id_value else None
        except ValueError as exc:
            raise DomainAPIException(
                code="analytics.invalid_event_id",
                message="event_id must be an integer.",
            ) from exc

        distribution = compute_checkin_distribution(
            organization=request.organization,
            event_id=event_id,
        )
        return Response({"event_id": event_id, "buckets": distribution})
