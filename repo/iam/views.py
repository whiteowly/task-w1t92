from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.constants import RoleCode
from common.permissions import ActionRolePermission, IsOrganizationMember
from iam.models import Role, UserOrganizationRole
from iam.serializers import (
    LoginSerializer,
    PasswordChangeSerializer,
    RoleAssignmentSerializer,
    UserSerializer,
)
from iam.services import (
    authenticate_with_lockout,
    create_auth_session,
    revoke_session,
    revoke_user_sessions,
)
from observability.services import log_audit_event
from tenancy.models import Organization

User = get_user_model()


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth_login"

    def _invalid_credentials_response(self, request):
        return Response(
            {
                "error": {
                    "code": "auth.invalid_credentials",
                    "message": "Invalid username or password.",
                    "details": [],
                    "request_id": getattr(request, "request_id", None),
                    "timestamp": timezone.now().isoformat(),
                }
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        organization = Organization.objects.filter(
            slug=serializer.validated_data["organization_slug"],
            is_active=True,
        ).first()
        if organization is None:
            return self._invalid_credentials_response(request)

        user, reason, wait_seconds = authenticate_with_lockout(
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
            organization=organization,
        )
        if user is None:
            if reason == "locked":
                return Response(
                    {
                        "error": {
                            "code": "auth.locked",
                            "message": "Account is temporarily locked.",
                            "details": [
                                {
                                    "field": "username",
                                    "code": "locked",
                                    "message": f"Retry in {wait_seconds} seconds.",
                                }
                            ],
                            "request_id": getattr(request, "request_id", None),
                            "timestamp": timezone.now().isoformat(),
                        }
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            return self._invalid_credentials_response(request)

        auth_session = create_auth_session(
            user=user,
            organization=organization,
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

        role_codes = list(
            UserOrganizationRole.objects.filter(
                user=user,
                organization=organization,
                is_active=True,
            )
            .select_related("role")
            .values_list("role__code", flat=True)
        )

        log_audit_event(
            action="auth.login",
            organization=organization,
            actor_user=user,
            request=request,
            result="success",
            metadata={"role_codes": role_codes},
        )

        return Response(
            {
                "session_key": auth_session.session_key,
                "expires_at": auth_session.expires_at,
                "organization": {
                    "id": organization.id,
                    "name": organization.name,
                    "slug": organization.slug,
                },
                "roles": role_codes,
            }
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        auth_session = getattr(request, "auth_session", None)
        if auth_session:
            revoke_session(auth_session=auth_session, reason="user_logout")
            log_audit_event(
                action="auth.logout",
                organization=getattr(request, "organization", None),
                actor_user=request.user,
                request=request,
                result="success",
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        if not request.user.check_password(serializer.validated_data["old_password"]):
            return Response(
                {
                    "error": {
                        "code": "auth.old_password_invalid",
                        "message": "Current password is invalid.",
                        "details": [],
                        "request_id": getattr(request, "request_id", None),
                        "timestamp": timezone.now().isoformat(),
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password", "updated_at"])
        revoke_user_sessions(user=request.user, reason="password_changed")

        log_audit_event(
            action="auth.password_changed",
            organization=getattr(request, "organization", None),
            actor_user=request.user,
            request=request,
            result="success",
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        organization = getattr(request, "organization", None)
        roles = getattr(request, "role_codes", [])
        return Response(
            {
                "id": request.user.id,
                "username": request.user.username,
                "full_name": request.user.full_name,
                "organization": {
                    "id": organization.id,
                    "slug": organization.slug,
                    "name": organization.name,
                }
                if organization
                else None,
                "roles": roles,
            }
        )


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [RoleCode.ADMINISTRATOR.value],
        "retrieve": [RoleCode.ADMINISTRATOR.value],
        "create": [RoleCode.ADMINISTRATOR.value],
        "update": [RoleCode.ADMINISTRATOR.value],
        "partial_update": [RoleCode.ADMINISTRATOR.value],
        "destroy": [RoleCode.ADMINISTRATOR.value],
        "assign_role": [RoleCode.ADMINISTRATOR.value],
        "revoke_role": [RoleCode.ADMINISTRATOR.value],
    }

    def get_queryset(self):
        organization = getattr(self.request, "organization", None)
        if organization is None:
            return User.objects.none()
        user_ids = UserOrganizationRole.objects.filter(
            organization=organization, is_active=True
        ).values_list("user_id", flat=True)
        return User.objects.filter(id__in=user_ids).order_by("username")

    def perform_create(self, serializer):
        password = serializer.validated_data.pop("password", None)
        role_codes = serializer.validated_data.pop("roles", [])
        user = serializer.save()
        if password:
            user.set_password(password)
            user.save(update_fields=["password", "updated_at"])
        organization = self.request.organization
        for code in role_codes:
            role = Role.objects.get(code=code)
            UserOrganizationRole.objects.get_or_create(
                user=user,
                organization=organization,
                role=role,
                defaults={"is_active": True},
            )
        log_audit_event(
            action="user.create",
            organization=organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="user",
            resource_id=str(user.id),
            metadata={"role_codes": role_codes},
        )

    def perform_update(self, serializer):
        password = serializer.validated_data.pop("password", None)
        role_codes = serializer.validated_data.pop("roles", None)
        user = serializer.save()
        if password:
            user.set_password(password)
            user.save(update_fields=["password", "updated_at"])
        organization = self.request.organization
        if role_codes is not None:
            UserOrganizationRole.objects.filter(
                user=user, organization=organization
            ).update(is_active=False)
            for code in role_codes:
                role = Role.objects.get(code=code)
                obj, created = UserOrganizationRole.objects.get_or_create(
                    user=user,
                    organization=organization,
                    role=role,
                    defaults={"is_active": True},
                )
                if not created:
                    obj.is_active = True
                    obj.save(update_fields=["is_active", "updated_at"])
        log_audit_event(
            action="user.update",
            organization=organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="user",
            resource_id=str(user.id),
        )

    def perform_destroy(self, instance):
        organization = self.request.organization
        user_id = instance.id
        UserOrganizationRole.objects.filter(
            user=instance, organization=organization
        ).update(is_active=False)
        log_audit_event(
            action="user.deactivate",
            organization=organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="user",
            resource_id=str(user_id),
        )

    @action(detail=True, methods=["post"], url_path="assign-role")
    def assign_role(self, request, pk=None):
        user = self.get_object()
        serializer = RoleAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = Role.objects.get(code=serializer.validated_data["role_code"])
        organization = request.organization
        obj, created = UserOrganizationRole.objects.get_or_create(
            user=user,
            organization=organization,
            role=role,
            defaults={"is_active": True},
        )
        if not created and not obj.is_active:
            obj.is_active = True
            obj.save(update_fields=["is_active", "updated_at"])
        log_audit_event(
            action="user.role.assign",
            organization=organization,
            actor_user=request.user,
            request=request,
            resource_type="user_organization_role",
            resource_id=str(obj.id),
            metadata={"role_code": role.code, "user_id": user.id},
        )
        return Response({"detail": "Role assigned."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="revoke-role")
    def revoke_role(self, request, pk=None):
        user = self.get_object()
        serializer = RoleAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = Role.objects.get(code=serializer.validated_data["role_code"])
        organization = request.organization
        updated = UserOrganizationRole.objects.filter(
            user=user, organization=organization, role=role, is_active=True
        ).update(is_active=False, updated_at=timezone.now())
        if updated:
            log_audit_event(
                action="user.role.revoke",
                organization=organization,
                actor_user=request.user,
                request=request,
                resource_type="user_organization_role",
                resource_id="",
                metadata={"role_code": role.code, "user_id": user.id},
            )
        return Response({"detail": "Role revoked."}, status=status.HTTP_200_OK)
