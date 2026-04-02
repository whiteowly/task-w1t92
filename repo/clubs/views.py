from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from clubs.models import Club, Department, Membership
from clubs.serializers import (
    ClubSerializer,
    DepartmentSerializer,
    MembershipJoinSerializer,
    MembershipLeaveSerializer,
    MembershipSerializer,
    MembershipStatusChangeSerializer,
    MembershipStatusLogSerializer,
    MembershipTransferSerializer,
)
from clubs.services import (
    change_membership_status,
    join_membership,
    leave_membership,
    transfer_membership,
)
from common.constants import RoleCode
from common.mixins import OrganizationScopedViewSetMixin
from common.permissions import HasOrganizationRole, IsOrganizationMember


MANAGER_ROLES = [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value]


class ClubViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Club.objects.all()
    serializer_class = ClubSerializer
    permission_classes = [IsOrganizationMember, HasOrganizationRole]
    required_roles = MANAGER_ROLES


class DepartmentViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Department.objects.select_related("club").all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsOrganizationMember, HasOrganizationRole]
    required_roles = MANAGER_ROLES

    def get_queryset(self):
        queryset = super().get_queryset()
        club_id = self.request.query_params.get("club_id")
        if club_id:
            queryset = queryset.filter(club_id=club_id)
        return queryset


class MembershipViewSet(OrganizationScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Membership.objects.select_related("member", "club", "department").all()
    serializer_class = MembershipSerializer
    permission_classes = [IsOrganizationMember, HasOrganizationRole]
    required_roles = MANAGER_ROLES

    def get_serializer_class(self):
        if self.action == "join":
            return MembershipJoinSerializer
        if self.action == "leave":
            return MembershipLeaveSerializer
        if self.action == "transfer":
            return MembershipTransferSerializer
        if self.action == "status_change":
            return MembershipStatusChangeSerializer
        if self.action == "status_log":
            return MembershipStatusLogSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        queryset = super().get_queryset()
        club_id = self.request.query_params.get("club_id")
        if club_id:
            queryset = queryset.filter(club_id=club_id)
        member_id = self.request.query_params.get("member_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        return queryset

    @action(detail=False, methods=["post"], url_path="join")
    def join(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = join_membership(
            organization=request.organization,
            member=serializer.validated_data["member"],
            club=serializer.validated_data["club"],
            department=serializer.validated_data.get("department"),
            reason_code=serializer.validated_data["reason_code"],
            effective_date=serializer.validated_data["effective_date"],
            actor=request.user,
            request=request,
        )
        response_serializer = MembershipSerializer(result.membership)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="leave")
    def leave(self, request, pk=None):
        membership = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        membership = leave_membership(
            membership=membership,
            reason_code=serializer.validated_data["reason_code"],
            effective_date=serializer.validated_data["effective_date"],
            actor=request.user,
            request=request,
        )
        return Response(MembershipSerializer(membership).data)

    @action(detail=True, methods=["post"], url_path="transfer")
    def transfer(self, request, pk=None):
        membership = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        membership = transfer_membership(
            membership=membership,
            to_club=serializer.validated_data["to_club"],
            to_department=serializer.validated_data.get("to_department"),
            reason_code=serializer.validated_data["reason_code"],
            effective_date=serializer.validated_data["effective_date"],
            actor=request.user,
            request=request,
        )
        return Response(MembershipSerializer(membership).data)

    @action(detail=True, methods=["post"], url_path="status-change")
    def status_change(self, request, pk=None):
        membership = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        membership = change_membership_status(
            membership=membership,
            to_status=serializer.validated_data["to_status"],
            reason_code=serializer.validated_data["reason_code"],
            effective_date=serializer.validated_data["effective_date"],
            actor=request.user,
            request=request,
        )
        return Response(MembershipSerializer(membership).data)

    @action(detail=True, methods=["get"], url_path="status-log")
    def status_log(self, request, pk=None):
        membership = self.get_object()
        logs = membership.status_logs.select_related("changed_by").order_by(
            "-effective_date", "-created_at"
        )
        serializer = self.get_serializer(logs, many=True)
        return Response(serializer.data)
