from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.mixins import OrganizationScopedViewSetMixin
from common.permissions import ActionRolePermission, IsOrganizationMember
from common.roles import (
    GROUP_LEADER_ROLE_CODE,
    MANAGER_ROLE_CODES,
    MEMBER_ROLE_CODE,
    REVIEWER_ROLE_CODES,
    ROLE_PERMISSIONS_MAP,
)
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


class WarehouseViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = ROLE_PERMISSIONS_MAP["logistics"]["WarehouseViewSet"]

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
    action_roles = ROLE_PERMISSIONS_MAP["logistics"]["ZoneViewSet"]

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
    action_roles = ROLE_PERMISSIONS_MAP["logistics"]["LocationViewSet"]

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


def _assert_group_leader_assigned(request, pickup_point):
    role_codes = set(getattr(request, "role_codes", []))
    if role_codes.intersection(MANAGER_ROLE_CODES):
        return
    if pickup_point.assigned_group_leader_id != request.user.id:
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("You can only modify pickup points assigned to you.")


class PickupPointViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = PickupPoint.objects.select_related("assigned_group_leader").all()
    serializer_class = PickupPointSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = ROLE_PERMISSIONS_MAP["logistics"]["PickupPointViewSet"]

    def get_queryset(self):
        queryset = super().get_queryset()
        role_codes = set(getattr(self.request, "role_codes", []))
        if role_codes.intersection(MANAGER_ROLE_CODES):
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
        _assert_group_leader_assigned(self.request, serializer.instance)
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
    action_roles = ROLE_PERMISSIONS_MAP["logistics"]["PickupPointBusinessHourViewSet"]

    def get_queryset(self):
        queryset = super().get_queryset()
        role_codes = set(getattr(self.request, "role_codes", []))
        if role_codes.intersection(MANAGER_ROLE_CODES):
            return queryset
        return queryset.filter(pickup_point__assigned_group_leader=self.request.user)


class PickupPointClosureViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = PickupPointClosure.objects.select_related("pickup_point").all()
    serializer_class = PickupPointClosureSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = ROLE_PERMISSIONS_MAP["logistics"]["PickupPointClosureViewSet"]

    def get_queryset(self):
        queryset = super().get_queryset()
        role_codes = set(getattr(self.request, "role_codes", []))
        if role_codes.intersection(MANAGER_ROLE_CODES):
            return queryset
        return queryset.filter(pickup_point__assigned_group_leader=self.request.user)

    def perform_create(self, serializer):
        pickup_point = serializer.validated_data["pickup_point"]
        _assert_group_leader_assigned(self.request, pickup_point)
        closure = serializer.save(organization=self.get_organization())
        log_audit_event(
            action="pickup_point_closure.create",
            organization=closure.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="pickup_point_closure",
            resource_id=str(closure.id),
        )

    def perform_update(self, serializer):
        _assert_group_leader_assigned(self.request, serializer.instance.pickup_point)
        closure = serializer.save()
        log_audit_event(
            action="pickup_point_closure.update",
            organization=closure.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="pickup_point_closure",
            resource_id=str(closure.id),
        )

    def perform_destroy(self, instance):
        _assert_group_leader_assigned(self.request, instance.pickup_point)
        closure_id = instance.id
        organization = instance.organization
        super().perform_destroy(instance)
        log_audit_event(
            action="pickup_point_closure.delete",
            organization=organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="pickup_point_closure",
            resource_id=str(closure_id),
        )


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
    action_roles = ROLE_PERMISSIONS_MAP["logistics"]["GroupLeaderOnboardingViewSet"]

    def get_serializer_class(self):
        if self.action == "review":
            return GroupLeaderOnboardingReviewSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        queryset = super().get_queryset()
        role_codes = set(getattr(self.request, "role_codes", []))
        if role_codes.intersection(MANAGER_ROLE_CODES | REVIEWER_ROLE_CODES):
            return queryset
        if GROUP_LEADER_ROLE_CODE in role_codes or MEMBER_ROLE_CODE in role_codes:
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
