from decimal import Decimal

from rest_framework import serializers

from finance.models import (
    CommissionModel,
    CommissionRule,
    LedgerEntry,
    Settlement,
    WithdrawalBlacklist,
    WithdrawalRequest,
    WithdrawalStatus,
)


class CommissionRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommissionRule
        fields = [
            "id",
            "model_type",
            "fixed_amount",
            "percentage",
            "tenant_cap_amount",
            "effective_from",
            "effective_to",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        model_type = attrs.get("model_type", getattr(self.instance, "model_type", None))
        fixed_amount = attrs.get(
            "fixed_amount", getattr(self.instance, "fixed_amount", None)
        )
        percentage = attrs.get("percentage", getattr(self.instance, "percentage", None))
        tenant_cap_amount = attrs.get(
            "tenant_cap_amount", getattr(self.instance, "tenant_cap_amount", None)
        )
        effective_from = attrs.get(
            "effective_from", getattr(self.instance, "effective_from", None)
        )
        effective_to = attrs.get(
            "effective_to", getattr(self.instance, "effective_to", None)
        )

        if tenant_cap_amount is not None and tenant_cap_amount <= 0:
            raise serializers.ValidationError(
                {"tenant_cap_amount": "Tenant cap must be greater than zero."}
            )

        if model_type == CommissionModel.FIXED_PER_ORDER:
            if fixed_amount is None or fixed_amount <= 0:
                raise serializers.ValidationError(
                    {"fixed_amount": "Fixed amount must be provided and > 0."}
                )
            attrs["percentage"] = None
        elif model_type == CommissionModel.PERCENTAGE_ELIGIBLE:
            if percentage is None or percentage <= 0 or percentage > Decimal("100"):
                raise serializers.ValidationError(
                    {"percentage": "Percentage must be > 0 and <= 100."}
                )
            attrs["fixed_amount"] = None

        if effective_from and effective_to and effective_to < effective_from:
            raise serializers.ValidationError(
                {"effective_to": "Effective end date must be on or after start date."}
            )

        return attrs


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "entry_type",
            "amount",
            "direction",
            "reference_type",
            "reference_id",
            "occurred_at",
            "metadata",
            "created_at",
        ]


class SettlementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Settlement
        fields = [
            "id",
            "period_year",
            "period_month",
            "generated_at",
            "hold_until",
            "status",
            "total_amount",
            "source_metadata",
            "created_at",
        ]


class SettlementGenerateSerializer(serializers.Serializer):
    run_at = serializers.DateTimeField(required=False)


class WithdrawalBlacklistSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalBlacklist
        fields = ["id", "user", "reason", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalRequest
        fields = [
            "id",
            "requester",
            "amount",
            "requested_at",
            "status",
            "requires_reviewer_approval",
            "review_notes",
            "reviewed_at",
            "reviewed_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "requested_at",
            "status",
            "requires_reviewer_approval",
            "review_notes",
            "reviewed_at",
            "reviewed_by",
            "created_at",
            "updated_at",
        ]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Withdrawal amount must be greater than zero."
            )
        return value

    def validate(self, attrs):
        requester = attrs["requester"]
        request = self.context["request"]
        if (
            requester.organization_roles.filter(
                organization=request.organization,
                is_active=True,
            ).exists()
            is False
        ):
            raise serializers.ValidationError(
                {"requester": "Requester must belong to active organization."}
            )
        return attrs


class WithdrawalReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=[WithdrawalStatus.APPROVED, WithdrawalStatus.REJECTED]
    )
    review_notes = serializers.CharField(required=False, allow_blank=True)
