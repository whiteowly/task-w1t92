from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.constants import RoleCode
from common.exceptions import DomainAPIException
from tenancy.models import TenantConfigVersion
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
