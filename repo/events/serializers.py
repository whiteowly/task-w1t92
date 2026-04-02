from django.contrib.auth import get_user_model
from rest_framework import serializers

from clubs.models import MemberStatus, Membership
from events.models import (
    Event,
    EventAttendanceReconciliation,
    EventCheckIn,
    EventRegistration,
    EventResourceDownload,
)

User = get_user_model()


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            "id",
            "club",
            "title",
            "starts_at",
            "ends_at",
            "eligible_member_count_snapshot",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "eligible_member_count_snapshot",
            "created_at",
            "updated_at",
        ]

    def validate_club(self, value):
        request = self.context["request"]
        if value.organization_id != request.organization.id:
            raise serializers.ValidationError("Club is outside of active organization.")
        return value

    def validate(self, attrs):
        starts_at = attrs.get("starts_at") or getattr(self.instance, "starts_at", None)
        ends_at = attrs.get("ends_at") or getattr(self.instance, "ends_at", None)
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError(
                {"ends_at": "Event end time must be after start time."}
            )
        return attrs

    def create(self, validated_data):
        validated_data["eligible_member_count_snapshot"] = Membership.objects.filter(
            organization=validated_data["organization"],
            club=validated_data["club"],
            status=MemberStatus.ACTIVE,
        ).count()
        return super().create(validated_data)

    def update(self, instance, validated_data):
        club = validated_data.get("club", instance.club)
        validated_data["eligible_member_count_snapshot"] = Membership.objects.filter(
            organization=instance.organization,
            club=club,
            status=MemberStatus.ACTIVE,
        ).count()
        return super().update(instance, validated_data)


class EventRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventRegistration
        fields = ["id", "event", "member", "registered_at", "created_at"]
        read_only_fields = ["id", "registered_at", "created_at"]

    def validate(self, attrs):
        request = self.context["request"]
        if attrs["event"].organization_id != request.organization.id:
            raise serializers.ValidationError(
                {"event": "Event is outside of active organization."}
            )
        return attrs


class EventCheckInSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventCheckIn
        fields = ["id", "event", "member", "checked_in_at", "created_at"]
        read_only_fields = ["id", "checked_in_at", "created_at"]

    def validate(self, attrs):
        request = self.context["request"]
        if attrs["event"].organization_id != request.organization.id:
            raise serializers.ValidationError(
                {"event": "Event is outside of active organization."}
            )
        return attrs


class EventAttendanceReconciliationSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventAttendanceReconciliation
        fields = [
            "id",
            "event",
            "member",
            "action",
            "reason_code",
            "notes",
            "reconciled_by",
            "reconciled_at",
            "created_at",
        ]
        read_only_fields = ["id", "reconciled_by", "reconciled_at", "created_at"]

    def validate(self, attrs):
        request = self.context["request"]
        if attrs["event"].organization_id != request.organization.id:
            raise serializers.ValidationError(
                {"event": "Event is outside of active organization."}
            )
        return attrs


class EventResourceDownloadSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventResourceDownload
        fields = [
            "id",
            "event",
            "member",
            "resource_key",
            "downloaded_at",
            "created_at",
        ]
        read_only_fields = ["id", "downloaded_at", "created_at"]

    def validate(self, attrs):
        request = self.context["request"]
        if attrs["event"].organization_id != request.organization.id:
            raise serializers.ValidationError(
                {"event": "Event is outside of active organization."}
            )
        return attrs
