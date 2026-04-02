from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from iam.models import AuthSession, LoginFailure, Role, UserOrganizationRole
from tenancy.models import Organization

User = get_user_model()


class AuthSessionApiTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Auth Org",
            slug="auth-org",
            timezone="UTC",
        )
        self.other_org = Organization.objects.create(
            name="Other Auth Org",
            slug="other-auth-org",
            timezone="UTC",
        )
        self.password = "ValidPass123!"

        self.user = User.objects.create_user(
            username="auth-user",
            password=self.password,
            full_name="Auth User",
        )
        self.outsider = User.objects.create_user(
            username="other-org-user",
            password=self.password,
        )

        self._assign_role(self.user, self.org, "member")
        self._assign_role(self.outsider, self.other_org, "member")

        self.anon_client = APIClient()

    def _assign_role(self, user, organization, role_code):
        role = Role.objects.get(code=role_code)
        UserOrganizationRole.objects.create(
            user=user,
            organization=organization,
            role=role,
        )

    def _login(self, *, organization_slug, username, password):
        return self.anon_client.post(
            "/api/v1/auth/login/",
            {
                "organization_slug": organization_slug,
                "username": username,
                "password": password,
            },
            format="json",
        )

    def _session_client(self, session_key):
        client = APIClient()
        client.credentials(HTTP_X_SESSION_KEY=session_key)
        return client

    def test_login_me_logout_flow_revokes_session(self):
        login_resp = self._login(
            organization_slug=self.org.slug,
            username=self.user.username,
            password=self.password,
        )
        self.assertEqual(login_resp.status_code, 200)
        session_key = login_resp.json()["session_key"]

        me_client = self._session_client(session_key)
        me_resp = me_client.get("/api/v1/auth/me/")
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.json()["username"], self.user.username)
        self.assertEqual(me_resp.json()["organization"]["slug"], self.org.slug)

        logout_resp = me_client.post("/api/v1/auth/logout/", {}, format="json")
        self.assertEqual(logout_resp.status_code, 204)

        session = AuthSession.objects.get(session_key=session_key)
        self.assertIsNotNone(session.revoked_at)
        self.assertEqual(session.revoked_reason, "user_logout")

        revoked_me_resp = me_client.get("/api/v1/auth/me/")
        self.assertEqual(revoked_me_resp.status_code, 403)

    def test_password_change_revokes_all_sessions_and_rotates_credentials(self):
        login_one = self._login(
            organization_slug=self.org.slug,
            username=self.user.username,
            password=self.password,
        )
        self.assertEqual(login_one.status_code, 200)
        login_two = self._login(
            organization_slug=self.org.slug,
            username=self.user.username,
            password=self.password,
        )
        self.assertEqual(login_two.status_code, 200)

        new_password = "FreshPass456!"
        primary_client = self._session_client(login_one.json()["session_key"])
        password_change_resp = primary_client.post(
            "/api/v1/auth/password/change/",
            {
                "old_password": self.password,
                "new_password": new_password,
            },
            format="json",
        )
        self.assertEqual(password_change_resp.status_code, 204)

        active_session_count = AuthSession.objects.filter(
            user=self.user,
            revoked_at__isnull=True,
        ).count()
        self.assertEqual(active_session_count, 0)

        revoked_reasons = set(
            AuthSession.objects.filter(user=self.user).values_list(
                "revoked_reason", flat=True
            )
        )
        self.assertEqual(revoked_reasons, {"password_changed"})

        secondary_client = self._session_client(login_two.json()["session_key"])
        revoked_me_resp = secondary_client.get("/api/v1/auth/me/")
        self.assertEqual(revoked_me_resp.status_code, 403)

        old_password_login = self._login(
            organization_slug=self.org.slug,
            username=self.user.username,
            password=self.password,
        )
        self.assertEqual(old_password_login.status_code, 401)
        self.assertEqual(
            old_password_login.json()["error"]["code"],
            "auth.invalid_credentials",
        )

        new_password_login = self._login(
            organization_slug=self.org.slug,
            username=self.user.username,
            password=new_password,
        )
        self.assertEqual(new_password_login.status_code, 200)

    def test_login_lockout_applies_after_threshold(self):
        for _ in range(settings.LOGIN_LOCKOUT_THRESHOLD):
            invalid = self._login(
                organization_slug=self.org.slug,
                username=self.user.username,
                password="WrongPass999!",
            )
            self.assertEqual(invalid.status_code, 401)
            self.assertEqual(
                invalid.json()["error"]["code"], "auth.invalid_credentials"
            )

        locked = self._login(
            organization_slug=self.org.slug,
            username=self.user.username,
            password=self.password,
        )
        self.assertEqual(locked.status_code, 429)
        self.assertEqual(locked.json()["error"]["code"], "auth.locked")

        failure = LoginFailure.objects.get(
            username=self.user.username, organization=self.org
        )
        self.assertTrue(failure.is_locked())

    def test_login_rejects_user_outside_requested_organization(self):
        response = self._login(
            organization_slug=self.org.slug,
            username=self.outsider.username,
            password=self.password,
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "auth.not_in_organization")
