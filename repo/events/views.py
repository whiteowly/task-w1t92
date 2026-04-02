from rest_framework import mixins, viewsets

from common.constants import RoleCode
from common.mixins import OrganizationScopedViewSetMixin
from common.permissions import HasOrganizationRole, IsOrganizationMember
from events.models import (
    Event,
    EventAttendanceReconciliation,
    EventCheckIn,
    EventRegistration,
    EventResourceDownload,
)
from events.serializers import (
    EventAttendanceReconciliationSerializer,
    EventCheckInSerializer,
    EventRegistrationSerializer,
    EventResourceDownloadSerializer,
    EventSerializer,
)
from events.services import (
    capture_checkin,
    reconcile_attendance,
    register_for_event,
    track_resource_download,
)
from observability.services import log_audit_event


EVENT_MANAGER_ROLES = [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value]
EVENT_REGISTRATION_ROLES = [
    RoleCode.ADMINISTRATOR.value,
    RoleCode.CLUB_MANAGER.value,
    RoleCode.MEMBER.value,
]
EVENT_CHECKIN_ROLES = EVENT_MANAGER_ROLES
EVENT_RESOURCE_DOWNLOAD_ROLES = [
    RoleCode.ADMINISTRATOR.value,
    RoleCode.CLUB_MANAGER.value,
    RoleCode.MEMBER.value,
]
MANAGER_ROLE_CODES = set(EVENT_MANAGER_ROLES)


def _limit_member_visibility_to_self(role_codes: set[str]) -> bool:
    is_manager = bool(role_codes & MANAGER_ROLE_CODES)
    is_member = RoleCode.MEMBER.value in role_codes
    return is_member and not is_manager


class EventViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Event.objects.select_related("club").all()
    serializer_class = EventSerializer
    permission_classes = [IsOrganizationMember, HasOrganizationRole]
    required_roles = EVENT_MANAGER_ROLES

    def perform_create(self, serializer):
        event = serializer.save(organization=self.get_organization())
        log_audit_event(
            action="event.create",
            organization=event.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="event",
            resource_id=str(event.id),
            metadata={"club_id": event.club_id, "title": event.title},
        )

    def perform_update(self, serializer):
        event_before = self.get_object()
        before_data = {
            "title": event_before.title,
            "starts_at": str(event_before.starts_at),
            "ends_at": str(event_before.ends_at),
        }
        event = serializer.save()
        log_audit_event(
            action="event.update",
            organization=event.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="event",
            resource_id=str(event.id),
            before_data=before_data,
            after_data={
                "title": event.title,
                "starts_at": str(event.starts_at),
                "ends_at": str(event.ends_at),
            },
        )

    def perform_destroy(self, instance):
        event_id = instance.id
        org = instance.organization
        title = instance.title
        super().perform_destroy(instance)
        log_audit_event(
            action="event.delete",
            organization=org,
            actor_user=self.request.user,
            request=self.request,
            resource_type="event",
            resource_id=str(event_id),
            metadata={"title": title},
        )


class EventRegistrationViewSet(
    OrganizationScopedViewSetMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = EventRegistration.objects.select_related("event", "member").all()
    serializer_class = EventRegistrationSerializer
    permission_classes = [IsOrganizationMember, HasOrganizationRole]
    required_roles = EVENT_REGISTRATION_ROLES

    def get_queryset(self):
        queryset = super().get_queryset()
        role_codes = set(getattr(self.request, "role_codes", []))
        if _limit_member_visibility_to_self(role_codes):
            queryset = queryset.filter(member=self.request.user)
        event_id = self.request.query_params.get("event_id")
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        return queryset

    def perform_create(self, serializer):
        registration = register_for_event(
            event=serializer.validated_data["event"],
            member=serializer.validated_data["member"],
            request=self.request,
        )
        serializer.instance = registration


class EventCheckInViewSet(
    OrganizationScopedViewSetMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = EventCheckIn.objects.select_related("event", "member").all()
    serializer_class = EventCheckInSerializer
    permission_classes = [IsOrganizationMember, HasOrganizationRole]
    required_roles = EVENT_CHECKIN_ROLES

    def get_queryset(self):
        queryset = super().get_queryset()
        role_codes = set(getattr(self.request, "role_codes", []))
        if _limit_member_visibility_to_self(role_codes):
            queryset = queryset.filter(member=self.request.user)
        event_id = self.request.query_params.get("event_id")
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        return queryset

    def perform_create(self, serializer):
        checkin = capture_checkin(
            event=serializer.validated_data["event"],
            member=serializer.validated_data["member"],
            request=self.request,
        )
        serializer.instance = checkin


class EventAttendanceReconciliationViewSet(
    OrganizationScopedViewSetMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = EventAttendanceReconciliation.objects.select_related(
        "event", "member", "reconciled_by"
    ).all()
    serializer_class = EventAttendanceReconciliationSerializer
    permission_classes = [IsOrganizationMember, HasOrganizationRole]
    required_roles = EVENT_MANAGER_ROLES

    def get_queryset(self):
        queryset = super().get_queryset()
        event_id = self.request.query_params.get("event_id")
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        return queryset

    def perform_create(self, serializer):
        reconciliation = reconcile_attendance(
            event=serializer.validated_data["event"],
            member=serializer.validated_data["member"],
            action=serializer.validated_data["action"],
            reason_code=serializer.validated_data["reason_code"],
            notes=serializer.validated_data.get("notes", ""),
            request=self.request,
        )
        serializer.instance = reconciliation


class EventResourceDownloadViewSet(
    OrganizationScopedViewSetMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = EventResourceDownload.objects.select_related("event", "member").all()
    serializer_class = EventResourceDownloadSerializer
    permission_classes = [IsOrganizationMember, HasOrganizationRole]
    required_roles = EVENT_RESOURCE_DOWNLOAD_ROLES

    def get_queryset(self):
        queryset = super().get_queryset()
        role_codes = set(getattr(self.request, "role_codes", []))
        if _limit_member_visibility_to_self(role_codes):
            queryset = queryset.filter(member=self.request.user)
        event_id = self.request.query_params.get("event_id")
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        return queryset

    def perform_create(self, serializer):
        download = track_resource_download(
            event=serializer.validated_data["event"],
            member=serializer.validated_data["member"],
            resource_key=serializer.validated_data["resource_key"],
            request=self.request,
        )
        serializer.instance = download
