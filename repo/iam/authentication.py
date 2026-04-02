from django.utils import timezone
from rest_framework import authentication, exceptions

from iam.models import AuthSession, UserOrganizationRole
from iam.services import touch_session


class OrganizationSessionAuthentication(authentication.BaseAuthentication):
    header_name = "HTTP_X_SESSION_KEY"

    def authenticate(self, request):
        session_key = request.META.get(self.header_name)
        if not session_key:
            return None

        try:
            auth_session = AuthSession.objects.select_related(
                "user", "organization"
            ).get(session_key=session_key)
        except AuthSession.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("Invalid session.") from exc

        if auth_session.revoked_at is not None:
            raise exceptions.AuthenticationFailed("Session has been revoked.")

        if auth_session.expires_at <= timezone.now():
            raise exceptions.AuthenticationFailed("Session has expired.")

        if not auth_session.user.is_active:
            raise exceptions.AuthenticationFailed("User account is inactive.")

        role_codes = list(
            UserOrganizationRole.objects.filter(
                user=auth_session.user,
                organization=auth_session.organization,
                is_active=True,
            )
            .select_related("role")
            .values_list("role__code", flat=True)
        )
        if not role_codes:
            raise exceptions.AuthenticationFailed(
                "No active role assignment for organization."
            )

        request.organization = auth_session.organization
        request.auth_session = auth_session
        request.role_codes = role_codes

        touch_session(auth_session)
        return auth_session.user, auth_session
