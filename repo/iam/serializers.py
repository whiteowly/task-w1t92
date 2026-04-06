from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from iam.models import Role, UserOrganizationRole

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    organization_slug = serializers.SlugField()
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_new_password(self, value):
        validate_password(value, user=self.context["request"].user)
        return value


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False, required=False)
    roles = serializers.ListField(
        child=serializers.CharField(), required=False, write_only=True
    )
    role_codes = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "full_name",
            "email",
            "is_active",
            "password",
            "roles",
            "role_codes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_role_codes(self, obj):
        organization = self.context["request"].organization
        return list(
            UserOrganizationRole.objects.filter(
                user=obj, organization=organization, is_active=True
            )
            .select_related("role")
            .values_list("role__code", flat=True)
        )

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_roles(self, value):
        valid_codes = set(Role.objects.values_list("code", flat=True))
        invalid = [v for v in value if v not in valid_codes]
        if invalid:
            raise serializers.ValidationError(f"Invalid role codes: {', '.join(invalid)}")
        return value


class RoleAssignmentSerializer(serializers.Serializer):
    role_code = serializers.CharField()

    def validate_role_code(self, value):
        if not Role.objects.filter(code=value).exists():
            raise serializers.ValidationError(f"Role '{value}' does not exist.")
        return value
