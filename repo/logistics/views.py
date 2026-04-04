from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from common.constants import RoleCode
from common.mixins import OrganizationScopedViewSetMixin
from common.permissions import IsOrganizationMember
from logistics.models import (
    GroupLeaderOnboarding,
    Location,
    PickupPoint,
    PickupPointBusinessHour,
    PickupPointClosure,
    Warehouse,
    Zone,
)
from logistics.serializers import (
    GroupLeaderOnboardingReviewSerializer,
    GroupLeaderOnboardingSerializer,
    LocationSerializer,
    PickupPointBusinessHourSerializer,
    PickupPointClosureSerializer,
    PickupPointSerializer,
    WarehouseSerializer,
    ZoneSerializer,
)
from logistics.services import (
    review_onboarding_application,
    submit_onboarding_application,
)
from observability.services import log_audit_event

MANAGER_ROLES = {RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value}
REVIEWER_ROLES = {RoleCode.COUNSELOR_REVIEWER.value}
GROUP_LEADER_ROLE = RoleCode.GROUP_LEADER.value


class ActionRolePermission(BasePermission):
    message = "Insufficient role for this action."

    def has_permission(self, request, view):
        action_roles = getattr(view, "action_roles", {})
        required = action_roles.get(getattr(view, "action", None))
        if not required:
            required = getattr(view, "required_roles", None)
        if not required:
            return True
        role_codes = set(getattr(request, "role_codes", []))
        return bool(role_codes.intersection(set(required)))


class WarehouseViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "retrieve": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "create": [RoleCode.ADMINISTRATOR.value],
        "update": [RoleCode.ADMINISTRATOR.value],
        "partial_update": [RoleCode.ADMINISTRATOR.value],
        "destroy": [RoleCode.ADMINISTRATOR.value],
    }

    def perform_create(self, serializer):
        warehouse = serializer.save(organization=self.get_organization())
        log_audit_event(
            action="warehouse.create",
            organization=warehouse.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="warehouse",
            resource_id=str(warehouse.id),
        )

    def perform_update(self, serializer):
        warehouse = serializer.save()
        log_audit_event(
            action="warehouse.update",
            organization=warehouse.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="warehouse",
            resource_id=str(warehouse.id),
        )

    def perform_destroy(self, instance):
        warehouse_id = instance.id
        organization = instance.organization
        super().perform_destroy(instance)
        log_audit_event(
            action="warehouse.delete",
            organization=organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="warehouse",
            resource_id=str(warehouse_id),
        )


class ZoneViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Zone.objects.select_related("warehouse").all()
    serializer_class = ZoneSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "retrieve": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "create": [RoleCode.ADMINISTRATOR.value],
        "update": [RoleCode.ADMINISTRATOR.value],
        "partial_update": [RoleCode.ADMINISTRATOR.value],
        "destroy": [RoleCode.ADMINISTRATOR.value],
    }

    def perform_create(self, serializer):
        zone = serializer.save(organization=self.get_organization())
        log_audit_event(
            action="zone.create",
            organization=zone.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="zone",
            resource_id=str(zone.id),
        )

    def perform_update(self, serializer):
        zone = serializer.save()
        log_audit_event(
            action="zone.update",
            organization=zone.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="zone",
            resource_id=str(zone.id),
        )

    def perform_destroy(self, instance):
        zone_id = instance.id
        organization = instance.organization
        super().perform_destroy(instance)
        log_audit_event(
            action="zone.delete",
            organization=organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="zone",
            resource_id=str(zone_id),
        )


class LocationViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Location.objects.select_related("zone", "zone__warehouse").all()
    serializer_class = LocationSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "retrieve": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "create": [RoleCode.ADMINISTRATOR.value],
        "update": [RoleCode.ADMINISTRATOR.value],
        "partial_update": [RoleCode.ADMINISTRATOR.value],
        "destroy": [RoleCode.ADMINISTRATOR.value],
    }

    def perform_create(self, serializer):
        location = serializer.save(organization=self.get_organization())
        log_audit_event(
            action="location.create",
            organization=location.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="location",
            resource_id=str(location.id),
        )

    def perform_update(self, serializer):
        location = serializer.save()
        log_audit_event(
            action="location.update",
            organization=location.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="location",
            resource_id=str(location.id),
        )

    def perform_destroy(self, instance):
        location_id = instance.id
        organization = instance.organization
        super().perform_destroy(instance)
        log_audit_event(
            action="location.delete",
            organization=organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="location",
            resource_id=str(location_id),
        )


class PickupPointViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = PickupPoint.objects.select_related("assigned_group_leader").all()
    serializer_class = PickupPointSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [
            RoleCode.ADMINISTRATOR.value,
            RoleCode.CLUB_MANAGER.value,
            RoleCode.GROUP_LEADER.value,
        ],
        "retrieve": [
            RoleCode.ADMINISTRATOR.value,
            RoleCode.CLUB_MANAGER.value,
            RoleCode.GROUP_LEADER.value,
        ],
        "create": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "update": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "partial_update": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "destroy": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        role_codes = set(getattr(self.request, "role_codes", []))
        if role_codes.intersection(MANAGER_ROLES):
            return queryset
        return queryset.filter(assigned_group_leader=self.request.user)

    def perform_create(self, serializer):
        pickup_point = serializer.save(organization=self.get_organization())
        log_audit_event(
            action="pickup_point.create",
            organization=pickup_point.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="pickup_point",
            resource_id=str(pickup_point.id),
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        log_audit_event(
            action="pickup_point.update",
            organization=instance.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="pickup_point",
            resource_id=str(instance.id),
        )

    def perform_destroy(self, instance):
        pickup_point_id = instance.id
        organization = instance.organization
        super().perform_destroy(instance)
        log_audit_event(
            action="pickup_point.delete",
            organization=organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="pickup_point",
            resource_id=str(pickup_point_id),
        )


class PickupPointBusinessHourViewSet(
    OrganizationScopedViewSetMixin, viewsets.ModelViewSet
):
    queryset = PickupPointBusinessHour.objects.select_related("pickup_point").all()
    serializer_class = PickupPointBusinessHourSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [
            RoleCode.ADMINISTRATOR.value,
            RoleCode.CLUB_MANAGER.value,
            RoleCode.GROUP_LEADER.value,
        ],
        "retrieve": [
            RoleCode.ADMINISTRATOR.value,
            RoleCode.CLUB_MANAGER.value,
            RoleCode.GROUP_LEADER.value,
        ],
        "create": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "update": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "partial_update": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "destroy": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        role_codes = set(getattr(self.request, "role_codes", []))
        if role_codes.intersection(MANAGER_ROLES):
            return queryset
        return queryset.filter(pickup_point__assigned_group_leader=self.request.user)


class PickupPointClosureViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = PickupPointClosure.objects.select_related("pickup_point").all()
    serializer_class = PickupPointClosureSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [
            RoleCode.ADMINISTRATOR.value,
            RoleCode.CLUB_MANAGER.value,
            RoleCode.GROUP_LEADER.value,
        ],
        "retrieve": [
            RoleCode.ADMINISTRATOR.value,
            RoleCode.CLUB_MANAGER.value,
            RoleCode.GROUP_LEADER.value,
        ],
        "create": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "update": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "partial_update": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "destroy": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        role_codes = set(getattr(self.request, "role_codes", []))
        if role_codes.intersection(MANAGER_ROLES):
            return queryset
        return queryset.filter(pickup_point__assigned_group_leader=self.request.user)


class GroupLeaderOnboardingViewSet(
    OrganizationScopedViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = GroupLeaderOnboarding.objects.select_related(
        "applicant", "pickup_point", "reviewed_by"
    ).all()
    serializer_class = GroupLeaderOnboardingSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [
            RoleCode.ADMINISTRATOR.value,
            RoleCode.CLUB_MANAGER.value,
            RoleCode.COUNSELOR_REVIEWER.value,
            RoleCode.GROUP_LEADER.value,
        ],
        "retrieve": [
            RoleCode.ADMINISTRATOR.value,
            RoleCode.CLUB_MANAGER.value,
            RoleCode.COUNSELOR_REVIEWER.value,
            RoleCode.GROUP_LEADER.value,
        ],
        "create": [
            RoleCode.ADMINISTRATOR.value,
            RoleCode.CLUB_MANAGER.value,
            RoleCode.COUNSELOR_REVIEWER.value,
            RoleCode.GROUP_LEADER.value,
            RoleCode.MEMBER.value,
        ],
        "review": [RoleCode.COUNSELOR_REVIEWER.value],
    }

    def get_serializer_class(self):
        if self.action == "review":
            return GroupLeaderOnboardingReviewSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        queryset = super().get_queryset()
        role_codes = set(getattr(self.request, "role_codes", []))
        if role_codes.intersection(MANAGER_ROLES | REVIEWER_ROLES):
            return queryset
        if GROUP_LEADER_ROLE in role_codes or RoleCode.MEMBER.value in role_codes:
            return queryset.filter(applicant=self.request.user)
        return queryset.none()

    def perform_create(self, serializer):
        application = submit_onboarding_application(
            organization=self.get_organization(),
            applicant=self.request.user,
            pickup_point=serializer.validated_data.get("pickup_point"),
            document_title=serializer.validated_data["document_title"],
            document_type=serializer.validated_data["document_type"],
            document_reference=serializer.validated_data["document_reference"],
            document_metadata=serializer.validated_data.get("document_metadata", {}),
            request=self.request,
        )
        serializer.instance = application

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        onboarding = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        onboarding = review_onboarding_application(
            application=onboarding,
            decision=serializer.validated_data["decision"],
            review_notes=serializer.validated_data.get("review_notes", ""),
            reviewer=request.user,
            request=request,
        )
        return Response(GroupLeaderOnboardingSerializer(onboarding).data)
