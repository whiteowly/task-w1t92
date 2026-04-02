from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from iam.models import UserOrganizationRole
from iam.serializers import LoginSerializer, PasswordChangeSerializer
from iam.services import (
    authenticate_with_lockout,
    create_auth_session,
    revoke_session,
    revoke_user_sessions,
)
from observability.services import log_audit_event
from tenancy.models import Organization


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth_login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        organization = Organization.objects.filter(
            slug=serializer.validated_data["organization_slug"],
            is_active=True,
        ).first()
        if organization is None:
            return Response(
                {
                    "error": {
                        "code": "auth.organization_not_found",
                        "message": "Organization not found.",
                        "details": [],
                        "request_id": getattr(request, "request_id", None),
                        "timestamp": timezone.now().isoformat(),
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

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
            code = (
                "auth.not_in_organization"
                if reason == "not_in_organization"
                else "auth.invalid_credentials"
            )
            message = (
                "User does not belong to the organization."
                if reason == "not_in_organization"
                else "Invalid username or password."
            )
            return Response(
                {
                    "error": {
                        "code": code,
                        "message": message,
                        "details": [],
                        "request_id": getattr(request, "request_id", None),
                        "timestamp": timezone.now().isoformat(),
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

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
