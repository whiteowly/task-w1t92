from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from common.constants import RoleCode
from common.mixins import OrganizationScopedViewSetMixin
from common.permissions import IsOrganizationMember
from finance.models import (
    CommissionRule,
    LedgerEntry,
    Settlement,
    WithdrawalBlacklist,
    WithdrawalRequest,
)
from finance.serializers import (
    CommissionRuleSerializer,
    LedgerEntrySerializer,
    SettlementGenerateSerializer,
    SettlementSerializer,
    WithdrawalBlacklistSerializer,
    WithdrawalRequestSerializer,
    WithdrawalReviewSerializer,
)
from finance.services import (
    create_withdrawal_request,
    generate_monthly_settlement,
    review_withdrawal_request,
)
from observability.services import log_audit_event

MANAGER_ROLES = {RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value}


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


class CommissionRuleViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = CommissionRule.objects.all()
    serializer_class = CommissionRuleSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [
            RoleCode.ADMINISTRATOR.value,
            RoleCode.CLUB_MANAGER.value,
            RoleCode.COUNSELOR_REVIEWER.value,
        ],
        "retrieve": [
            RoleCode.ADMINISTRATOR.value,
            RoleCode.CLUB_MANAGER.value,
            RoleCode.COUNSELOR_REVIEWER.value,
        ],
        "create": [RoleCode.ADMINISTRATOR.value],
        "update": [RoleCode.ADMINISTRATOR.value],
        "partial_update": [RoleCode.ADMINISTRATOR.value],
        "destroy": [RoleCode.ADMINISTRATOR.value],
    }

    def perform_create(self, serializer):
        rule = serializer.save(organization=self.get_organization())
        log_audit_event(
            action="commission_rule.create",
            organization=rule.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="commission_rule",
            resource_id=str(rule.id),
        )

    def perform_update(self, serializer):
        rule = serializer.save()
        log_audit_event(
            action="commission_rule.update",
            organization=rule.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="commission_rule",
            resource_id=str(rule.id),
        )

    def perform_destroy(self, instance):
        rule_id = instance.id
        organization = instance.organization
        super().perform_destroy(instance)
        log_audit_event(
            action="commission_rule.delete",
            organization=organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="commission_rule",
            resource_id=str(rule_id),
        )


class LedgerEntryViewSet(
    OrganizationScopedViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = LedgerEntry.objects.all().order_by("-occurred_at", "-id")
    serializer_class = LedgerEntrySerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [
            RoleCode.ADMINISTRATOR.value,
            RoleCode.CLUB_MANAGER.value,
            RoleCode.COUNSELOR_REVIEWER.value,
        ],
        "retrieve": [
            RoleCode.ADMINISTRATOR.value,
            RoleCode.CLUB_MANAGER.value,
            RoleCode.COUNSELOR_REVIEWER.value,
        ],
    }


class SettlementViewSet(
    OrganizationScopedViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Settlement.objects.all().order_by("-period_year", "-period_month")
    serializer_class = SettlementSerializer
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
        "generate": [RoleCode.ADMINISTRATOR.value],
    }

    @action(detail=False, methods=["post"])
    def generate(self, request):
        serializer = SettlementGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        settlement, created = generate_monthly_settlement(
            organization=request.organization,
            actor=request.user,
            request=request,
            run_at_utc=serializer.validated_data.get("run_at"),
        )
        return Response(
            {
                "created": created,
                "settlement": SettlementSerializer(settlement).data,
            },
            status=201 if created else 200,
        )


class WithdrawalBlacklistViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = WithdrawalBlacklist.objects.select_related("user").all()
    serializer_class = WithdrawalBlacklistSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "retrieve": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "create": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "update": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "partial_update": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "destroy": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
    }

    def perform_create(self, serializer):
        item = serializer.save(organization=self.get_organization())
        log_audit_event(
            action="withdrawal_blacklist.create",
            organization=item.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="withdrawal_blacklist",
            resource_id=str(item.id),
        )


class WithdrawalRequestViewSet(
    OrganizationScopedViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = WithdrawalRequest.objects.select_related(
        "requester", "reviewed_by"
    ).all()
    serializer_class = WithdrawalRequestSerializer
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
            RoleCode.GROUP_LEADER.value,
        ],
        "review": [RoleCode.COUNSELOR_REVIEWER.value],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        role_codes = set(getattr(self.request, "role_codes", []))
        if role_codes.intersection(
            {
                RoleCode.ADMINISTRATOR.value,
                RoleCode.CLUB_MANAGER.value,
                RoleCode.COUNSELOR_REVIEWER.value,
            }
        ):
            return queryset
        return queryset.filter(requester=self.request.user)

    def perform_create(self, serializer):
        role_codes = set(getattr(self.request, "role_codes", []))
        requester = serializer.validated_data["requester"]
        if (
            not role_codes.intersection(MANAGER_ROLES)
            and requester.id != self.request.user.id
        ):
            from common.exceptions import DomainAPIException

            raise DomainAPIException(
                code="withdrawal.requester_forbidden",
                message="You can only create withdrawal requests for your own account.",
                status_code=403,
            )

        request_obj = create_withdrawal_request(
            organization=self.get_organization(),
            requester=requester,
            amount=serializer.validated_data["amount"],
            actor=self.request.user,
            request=self.request,
        )
        serializer.instance = request_obj

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        withdrawal_request = self.get_object()
        serializer = WithdrawalReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reviewed = review_withdrawal_request(
            withdrawal_request=withdrawal_request,
            decision=serializer.validated_data["decision"],
            review_notes=serializer.validated_data.get("review_notes", ""),
            reviewer=request.user,
            request=request,
        )
        return Response(WithdrawalRequestSerializer(reviewed).data)
