from django.utils.dateparse import parse_datetime
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from common.constants import RoleCode
from common.exceptions import DomainAPIException
from common.mixins import OrganizationScopedViewSetMixin
from common.permissions import IsOrganizationMember
from observability.models import AuditLog, MetricsSnapshot, ReportExport
from observability.serializers import (
    AuditLogSerializer,
    MetricsSnapshotGenerateSerializer,
    MetricsSnapshotSerializer,
    ReportExportCreateSerializer,
    ReportExportSerializer,
)
from observability.services import create_metrics_snapshot, create_report_export


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


OBSERVABILITY_READ_ROLES = [
    RoleCode.ADMINISTRATOR.value,
    RoleCode.CLUB_MANAGER.value,
    RoleCode.COUNSELOR_REVIEWER.value,
]
OBSERVABILITY_WRITE_ROLES = [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value]


class AuditLogViewSet(
    OrganizationScopedViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = AuditLog.objects.select_related("organization", "actor_user").all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": OBSERVABILITY_READ_ROLES,
        "retrieve": OBSERVABILITY_READ_ROLES,
    }

    def get_queryset(self):
        queryset = super().get_queryset().order_by("-created_at", "-id")
        params = self.request.query_params
        action = (params.get("action") or "").strip()
        result = (params.get("result") or "").strip()
        resource_type = (params.get("resource_type") or "").strip()
        created_after = (params.get("created_after") or "").strip()
        created_before = (params.get("created_before") or "").strip()

        if action:
            queryset = queryset.filter(action=action)
        if result:
            queryset = queryset.filter(result=result)
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)
        if created_after:
            created_after_dt = parse_datetime(created_after)
            if created_after_dt is None:
                raise DomainAPIException(
                    code="observability.audit_logs.invalid_created_after",
                    message="created_after must be an ISO-8601 datetime.",
                )
            queryset = queryset.filter(created_at__gte=created_after_dt)
        if created_before:
            created_before_dt = parse_datetime(created_before)
            if created_before_dt is None:
                raise DomainAPIException(
                    code="observability.audit_logs.invalid_created_before",
                    message="created_before must be an ISO-8601 datetime.",
                )
            queryset = queryset.filter(created_at__lte=created_before_dt)
        return queryset


class MetricsSnapshotViewSet(
    OrganizationScopedViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = MetricsSnapshot.objects.select_related("organization").all()
    serializer_class = MetricsSnapshotSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": OBSERVABILITY_READ_ROLES,
        "retrieve": OBSERVABILITY_READ_ROLES,
        "generate": OBSERVABILITY_WRITE_ROLES,
    }

    def get_queryset(self):
        return super().get_queryset().order_by("-captured_at", "-id")

    @action(detail=False, methods=["post"])
    def generate(self, request):
        serializer = MetricsSnapshotGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        snapshot = create_metrics_snapshot(
            organization=request.organization,
            actor_user=request.user,
            request=request,
            metric_key=serializer.validated_data["metric_key"],
        )
        return Response(MetricsSnapshotSerializer(snapshot).data, status=201)


class ReportExportViewSet(
    OrganizationScopedViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = ReportExport.objects.select_related("organization").all()
    serializer_class = ReportExportSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": OBSERVABILITY_READ_ROLES,
        "retrieve": OBSERVABILITY_READ_ROLES,
        "create": OBSERVABILITY_WRITE_ROLES,
    }

    def get_queryset(self):
        return super().get_queryset().order_by("-created_at", "-id")

    def get_serializer_class(self):
        if self.action == "create":
            return ReportExportCreateSerializer
        return super().get_serializer_class()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        export = create_report_export(
            organization=request.organization,
            actor_user=request.user,
            request=request,
            report_type=serializer.validated_data["report_type"],
        )
        return Response(ReportExportSerializer(export).data, status=201)
