import re

from rest_framework import serializers

from common.pii import (
    decrypt_pii_value,
    encrypt_pii_value,
    mask_phone,
    mask_postal_code,
    mask_text,
)
from logistics.models import (
    GroupLeaderOnboarding,
    OnboardingStatus,
    Location,
    PickupPoint,
    PickupPointBusinessHour,
    PickupPointClosure,
    Warehouse,
    Zone,
)

US_STATE_PATTERN = re.compile(r"^[A-Z]{2}$")
US_POSTAL_PATTERN = re.compile(r"^\d{5}(-\d{4})?$")
US_PHONE_PATTERN = re.compile(r"^(\+?1)?\d{10}$")
RESTRICTED_HANDLING_ALLOWED_FLAGS = {
    "fragile",
    "hazmat",
    "oversized",
    "temperature_sensitive",
    "biohazard",
    "security_sealed",
}


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ["id", "name", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = ["id", "warehouse", "name", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_warehouse(self, value):
        request = self.context["request"]
        if value.organization_id != request.organization.id:
            raise serializers.ValidationError(
                "Warehouse is outside of active organization."
            )
        return value


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = [
            "id",
            "zone",
            "code",
            "length_in",
            "width_in",
            "height_in",
            "load_limit_lbs",
            "temperature_zone",
            "restricted_handling_flags",
            "capacity_slots",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_zone(self, value):
        request = self.context["request"]
        if value.organization_id != request.organization.id:
            raise serializers.ValidationError("Zone is outside of active organization.")
        return value

    def validate_restricted_handling_flags(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError(
                "Restricted handling flags must be a list of strings."
            )
        invalid = sorted(
            {
                str(flag)
                for flag in value
                if str(flag) not in RESTRICTED_HANDLING_ALLOWED_FLAGS
            }
        )
        if invalid:
            raise serializers.ValidationError(
                f"Unsupported restricted handling flags: {', '.join(invalid)}."
            )
        return list(dict.fromkeys([str(flag) for flag in value]))

    def validate(self, attrs):
        for field_name in ("length_in", "width_in", "height_in", "load_limit_lbs"):
            value = attrs.get(field_name)
            if value is not None and value <= 0:
                raise serializers.ValidationError(
                    {field_name: "Value must be greater than zero."}
                )

        capacity_slots = attrs.get("capacity_slots")
        if capacity_slots is not None and capacity_slots < 0:
            raise serializers.ValidationError(
                {"capacity_slots": "Capacity slots cannot be negative."}
            )

        return attrs


class PickupPointSerializer(serializers.ModelSerializer):
    PII_FIELDS = {
        "address_line1": (
            "encrypted_address_line1",
            lambda value: mask_text(value, keep_start=4),
        ),
        "address_line2": (
            "encrypted_address_line2",
            lambda value: mask_text(value, keep_start=2),
        ),
        "city": ("encrypted_city", lambda value: mask_text(value, keep_start=2)),
        "state": ("encrypted_state", lambda value: mask_text(value, keep_start=1)),
        "postal_code": ("encrypted_postal_code", mask_postal_code),
        "country": ("encrypted_country", lambda value: mask_text(value, keep_start=1)),
        "contact_phone": ("encrypted_contact_phone", mask_phone),
    }

    class Meta:
        model = PickupPoint
        fields = [
            "id",
            "name",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "country",
            "contact_phone",
            "capacity_limit",
            "assigned_group_leader",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_state(self, value):
        value = (value or "").upper()
        if not US_STATE_PATTERN.match(value):
            raise serializers.ValidationError(
                "State must be a two-letter US state code (e.g. CA)."
            )
        return value

    def validate_postal_code(self, value):
        if not US_POSTAL_PATTERN.match(value or ""):
            raise serializers.ValidationError(
                "Postal code must be ZIP or ZIP+4 format."
            )
        return value

    def validate_country(self, value):
        if (value or "").upper() != "US":
            raise serializers.ValidationError(
                "Pickup-point addresses currently support US country code only."
            )
        return "US"

    def validate_contact_phone(self, value):
        raw = (value or "").strip()
        if not raw:
            return ""
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if not US_PHONE_PATTERN.match(digits):
            raise serializers.ValidationError(
                "Contact phone must be a valid US number (10 digits)."
            )
        return digits

    def validate_capacity_limit(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Capacity limit must be greater than zero."
            )
        return value

    def validate_assigned_group_leader(self, value):
        if value is None:
            return value
        request = self.context["request"]
        role_codes = set(
            value.organization_roles.filter(
                organization=request.organization,
                is_active=True,
            ).values_list("role__code", flat=True)
        )
        if "group_leader" not in role_codes:
            raise serializers.ValidationError(
                "Assigned user must have an active group_leader role in this organization."
            )
        return value

    def _pop_pii_values(self, validated_data: dict) -> dict:
        pii_payload = {}
        for field_name in self.PII_FIELDS:
            if field_name in validated_data:
                pii_payload[field_name] = validated_data.pop(field_name)
        return pii_payload

    def _apply_pii_storage(self, instance: PickupPoint, pii_payload: dict) -> list[str]:
        update_fields: list[str] = []
        for plain_field, value in pii_payload.items():
            encrypted_field, masker = self.PII_FIELDS[plain_field]
            masked_value = masker(value)
            encrypted_value = encrypt_pii_value(value)
            setattr(instance, plain_field, masked_value)
            setattr(instance, encrypted_field, encrypted_value)
            update_fields.extend([plain_field, encrypted_field])
        return update_fields

    def create(self, validated_data):
        pii_payload = self._pop_pii_values(validated_data)
        if "contact_phone" not in pii_payload:
            pii_payload["contact_phone"] = ""
        for plain_field, value in pii_payload.items():
            _, masker = self.PII_FIELDS[plain_field]
            validated_data[plain_field] = masker(value)

        instance = super().create(validated_data)
        update_fields = self._apply_pii_storage(instance, pii_payload)
        if update_fields:
            instance.save(update_fields=[*set(update_fields), "updated_at"])
        return instance

    def update(self, instance, validated_data):
        pii_payload = self._pop_pii_values(validated_data)
        for plain_field, value in pii_payload.items():
            _, masker = self.PII_FIELDS[plain_field]
            validated_data[plain_field] = masker(value)

        instance = super().update(instance, validated_data)
        update_fields = self._apply_pii_storage(instance, pii_payload)
        if update_fields:
            instance.save(update_fields=[*set(update_fields), "updated_at"])
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for plain_field, (encrypted_field, masker) in self.PII_FIELDS.items():
            encrypted_value = getattr(instance, encrypted_field, "")
            if encrypted_value:
                try:
                    raw_value = decrypt_pii_value(encrypted_value)
                    data[plain_field] = masker(raw_value)
                    continue
                except ValueError:
                    pass
            data[plain_field] = masker(str(data.get(plain_field, "") or ""))
        return data


class PickupPointBusinessHourSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupPointBusinessHour
        fields = [
            "id",
            "pickup_point",
            "weekday",
            "opens_at",
            "closes_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        request = self.context["request"]
        pickup_point = attrs["pickup_point"]
        if pickup_point.organization_id != request.organization.id:
            raise serializers.ValidationError(
                {"pickup_point": "Pickup point is outside of active organization."}
            )
        if attrs["closes_at"] <= attrs["opens_at"]:
            raise serializers.ValidationError(
                {"closes_at": "Closing time must be later than opening time."}
            )
        return attrs


class PickupPointClosureSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupPointClosure
        fields = [
            "id",
            "pickup_point",
            "starts_at",
            "ends_at",
            "reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        request = self.context["request"]
        pickup_point = attrs["pickup_point"]
        if pickup_point.organization_id != request.organization.id:
            raise serializers.ValidationError(
                {"pickup_point": "Pickup point is outside of active organization."}
            )

        if attrs["ends_at"] <= attrs["starts_at"]:
            raise serializers.ValidationError(
                {"ends_at": "Closure end time must be after start time."}
            )
        return attrs


class GroupLeaderOnboardingSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupLeaderOnboarding
        fields = [
            "id",
            "applicant",
            "pickup_point",
            "status",
            "document_title",
            "document_type",
            "document_reference",
            "document_metadata",
            "submitted_at",
            "reviewed_at",
            "reviewed_by",
            "review_notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "applicant",
            "status",
            "submitted_at",
            "reviewed_at",
            "reviewed_by",
            "review_notes",
            "created_at",
            "updated_at",
        ]

    def validate_pickup_point(self, value):
        if value is None:
            return value
        request = self.context["request"]
        if value.organization_id != request.organization.id:
            raise serializers.ValidationError(
                "Pickup point is outside of active organization."
            )
        return value


class GroupLeaderOnboardingReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=[OnboardingStatus.APPROVED, OnboardingStatus.REJECTED]
    )
    review_notes = serializers.CharField(required=False, allow_blank=True)
