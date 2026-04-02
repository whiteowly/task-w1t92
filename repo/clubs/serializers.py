from django.contrib.auth import get_user_model
from rest_framework import serializers

from clubs.models import Club, Department, MemberStatus, Membership, MembershipStatusLog
from iam.models import UserOrganizationRole

User = get_user_model()


class ClubSerializer(serializers.ModelSerializer):
    class Meta:
        model = Club
        fields = ["id", "name", "code", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "club", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_club(self, value):
        request = self.context["request"]
        if value.organization_id != request.organization.id:
            raise serializers.ValidationError("Club is outside of active organization.")
        return value


class MembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = [
            "id",
            "member",
            "club",
            "department",
            "status",
            "status_effective_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "status_effective_date",
            "created_at",
            "updated_at",
        ]

    def validate_member(self, value):
        if not value.is_active:
            raise serializers.ValidationError("Member account must be active.")
        return value

    def validate_club(self, value):
        request = self.context["request"]
        if value.organization_id != request.organization.id:
            raise serializers.ValidationError("Club is outside of active organization.")
        return value

    def validate(self, attrs):
        request = self.context["request"]
        club = attrs.get("club") or getattr(self.instance, "club", None)
        department = attrs.get("department")

        if department is not None:
            if department.organization_id != request.organization.id:
                raise serializers.ValidationError(
                    {"department": "Department is outside of active organization."}
                )
            if club is not None and department.club_id != club.id:
                raise serializers.ValidationError(
                    {"department": "Department must belong to selected club."}
                )

        if self.instance and (
            "member" in attrs and attrs["member"].id != self.instance.member_id
        ):
            raise serializers.ValidationError(
                {
                    "member": "Use lifecycle workflows instead of changing member relationship."
                }
            )
        if (
            self.instance
            and "club" in attrs
            and attrs["club"].id != self.instance.club_id
        ):
            raise serializers.ValidationError(
                {"club": "Use transfer workflow instead of changing club directly."}
            )

        return attrs


class MembershipJoinSerializer(serializers.Serializer):
    member = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    club = serializers.PrimaryKeyRelatedField(queryset=Club.objects.all())
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True
    )
    reason_code = serializers.CharField(max_length=64)
    effective_date = serializers.DateField()

    def validate(self, attrs):
        request = self.context["request"]
        member = attrs["member"]
        club = attrs["club"]
        department = attrs.get("department")

        if not member.is_active:
            raise serializers.ValidationError(
                {"member": "Member account must be active."}
            )

        in_organization = UserOrganizationRole.objects.filter(
            user=member,
            organization=request.organization,
            is_active=True,
        ).exists()
        if not in_organization:
            raise serializers.ValidationError(
                {"member": "Member is outside of active organization."}
            )

        if club.organization_id != request.organization.id:
            raise serializers.ValidationError(
                {"club": "Club is outside of active organization."}
            )

        if department is not None:
            if department.organization_id != request.organization.id:
                raise serializers.ValidationError(
                    {"department": "Department is outside of active organization."}
                )
            if department.club_id != club.id:
                raise serializers.ValidationError(
                    {"department": "Department must belong to selected club."}
                )

        return attrs


class MembershipLeaveSerializer(serializers.Serializer):
    reason_code = serializers.CharField(max_length=64)
    effective_date = serializers.DateField()


class MembershipTransferSerializer(serializers.Serializer):
    to_club = serializers.PrimaryKeyRelatedField(queryset=Club.objects.all())
    to_department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True
    )
    reason_code = serializers.CharField(max_length=64)
    effective_date = serializers.DateField()

    def validate(self, attrs):
        request = self.context["request"]
        to_club = attrs["to_club"]
        to_department = attrs.get("to_department")

        if to_club.organization_id != request.organization.id:
            raise serializers.ValidationError(
                {"to_club": "Target club is outside of active organization."}
            )

        if to_department is not None:
            if to_department.organization_id != request.organization.id:
                raise serializers.ValidationError(
                    {
                        "to_department": "Target department is outside of active organization."
                    }
                )
            if to_department.club_id != to_club.id:
                raise serializers.ValidationError(
                    {"to_department": "Target department must belong to target club."}
                )
        return attrs


class MembershipStatusChangeSerializer(serializers.Serializer):
    to_status = serializers.ChoiceField(choices=MemberStatus.choices)
    reason_code = serializers.CharField(max_length=64)
    effective_date = serializers.DateField()


class MembershipStatusLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = MembershipStatusLog
        fields = [
            "id",
            "membership",
            "from_status",
            "to_status",
            "reason_code",
            "effective_date",
            "changed_by",
            "created_at",
        ]
