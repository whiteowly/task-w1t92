from rest_framework import status, viewsets
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.constants import RoleCode
from common.exceptions import DomainAPIException
from common.permissions import ActionRolePermission, IsOrganizationMember
from observability.services import log_audit_event
from tenancy.models import Organization, TenantConfigVersion
from tenancy.serializers import (
    OrganizationSerializer,
    TenantConfigRollbackSerializer,
    TenantConfigUpdateSerializer,
    TenantConfigVersionSerializer,
)
from tenancy.services import (
    get_latest_config_version,
    rollback_tenant_config,
    update_tenant_config,
)


class RolePermission(BasePermission):
    message = "Insufficient role for this action."

    def has_permission(self, request, view):
        required_roles = getattr(view, "required_roles", None)
        if not required_roles:
            return True
        role_codes = set(getattr(request, "role_codes", []))
        return bool(role_codes.intersection(set(required_roles)))


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [RoleCode.ADMINISTRATOR.value],
        "retrieve": [RoleCode.ADMINISTRATOR.value],
        "create": [RoleCode.ADMINISTRATOR.value],
        "update": [RoleCode.ADMINISTRATOR.value],
        "partial_update": [RoleCode.ADMINISTRATOR.value],
        "destroy": [RoleCode.ADMINISTRATOR.value],
    }

    def get_queryset(self):
        organization = getattr(self.request, "organization", None)
        if organization is None:
            return Organization.objects.none()
        return Organization.objects.filter(id=organization.id)

    def _enforce_active_tenant_object(self, organization: Organization):
        active_organization = getattr(self.request, "organization", None)
        if active_organization is None or organization.id != active_organization.id:
            raise DomainAPIException(
                code="organization.cross_tenant",
                message="Organization is outside your active tenant.",
                status_code=404,
            )

    def get_object(self):
        organization = super().get_object()
        self._enforce_active_tenant_object(organization)
        return organization

    def perform_create(self, serializer):
        raise DomainAPIException(
            code="organization.create_forbidden",
            message="Organizations can only be created through platform provisioning.",
            status_code=403,
        )

    def perform_update(self, serializer):
        self._enforce_active_tenant_object(serializer.instance)
        org = serializer.save()
        log_audit_event(
            action="organization.update",
            organization=self.request.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="organization",
            resource_id=str(org.id),
        )

    def perform_destroy(self, instance):
        self._enforce_active_tenant_object(instance)
        org_id = instance.id
        super().perform_destroy(instance)
        log_audit_event(
            action="organization.delete",
            organization=self.request.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="organization",
            resource_id=str(org_id),
        )


class CurrentOrganizationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        organization = getattr(request, "organization", None)
        if organization is None:
            return Response({"organization": None})
        return Response(OrganizationSerializer(organization).data)


class TenantConfigCurrentView(APIView):
    permission_classes = [IsAuthenticated, RolePermission]

    def get_required_roles(self):
        return [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value]

    @property
    def required_roles(self):
        return self.get_required_roles()

    def get(self, request):
        latest = get_latest_config_version(organization=request.organization)
        payload = latest.config_payload if latest else {}
        return Response(
            {
                "organization_id": request.organization.id,
                "current_version": latest.version_number if latest else 0,
                "config_payload": payload,
            }
        )

    def patch(self, request):
        if RoleCode.ADMINISTRATOR.value not in set(getattr(request, "role_codes", [])):
            raise DomainAPIException(
                code="tenant_config.forbidden",
                message="Only administrators can update tenant configuration.",
                status_code=403,
            )

        serializer = TenantConfigUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        version = update_tenant_config(
            organization=request.organization,
            actor=request.user,
            config_patch=serializer.validated_data["config_patch"],
            change_summary=serializer.validated_data.get("change_summary", ""),
            request=request,
        )
        return Response(TenantConfigVersionSerializer(version).data, status=201)


class TenantConfigVersionListView(APIView):
    permission_classes = [IsAuthenticated, RolePermission]
    required_roles = [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value]

    def get(self, request):
        versions = TenantConfigVersion.objects.filter(
            organization=request.organization
        ).order_by("-version_number")
        return Response(TenantConfigVersionSerializer(versions, many=True).data)


class TenantConfigRollbackView(APIView):
    permission_classes = [IsAuthenticated, RolePermission]
    required_roles = [RoleCode.ADMINISTRATOR.value]

    def post(self, request, version_id: int):
        serializer = TenantConfigRollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        source_version = TenantConfigVersion.objects.filter(
            organization=request.organization,
            id=version_id,
        ).first()
        if source_version is None:
            raise DomainAPIException(
                code="tenant_config.version_not_found",
                message="Config version not found for active organization.",
                status_code=404,
            )

        version = rollback_tenant_config(
            organization=request.organization,
            source_version=source_version,
            actor=request.user,
            change_summary=serializer.validated_data.get("change_summary", ""),
            request=request,
        )
        return Response(TenantConfigVersionSerializer(version).data, status=201)
