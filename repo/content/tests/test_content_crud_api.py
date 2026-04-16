from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from common.constants import RoleCode
from content.models import (
    ContentAsset,
    ContentChapter,
    ContentChapterACL,
    ContentEntitlement,
    ContentRedeemCode,
    ContentDownloadToken,
)
from iam.models import AuthSession, Role, UserOrganizationRole
from tenancy.models import Organization
import hashlib

User = get_user_model()


class ContentCrudApiTests(TestCase):
    """Tests for content chapters/chapter-acl/entitlements CRUD, redeem-codes list, download-tokens list."""

    def setUp(self):
        self.org = Organization.objects.create(
            name="Content CRUD Org", slug="content-crud-org", timezone="UTC"
        )
        self.other_org = Organization.objects.create(
            name="Content Other Org", slug="content-other-org", timezone="UTC"
        )
        self.password = "ValidPass123!"

        self.admin = User.objects.create_user(
            username="cc-admin", password=self.password, full_name="Admin"
        )
        self.member = User.objects.create_user(
            username="cc-member", password=self.password, full_name="Member"
        )
        self.other_admin = User.objects.create_user(
            username="cc-other-admin", password=self.password, full_name="Other Admin"
        )

        self._assign_role(self.admin, self.org, RoleCode.ADMINISTRATOR.value)
        self._assign_role(self.member, self.org, RoleCode.MEMBER.value)
        self._assign_role(
            self.other_admin, self.other_org, RoleCode.ADMINISTRATOR.value
        )

        self.admin_client = self._build_client(self.admin, self.org)
        self.member_client = self._build_client(self.member, self.org)
        self.other_admin_client = self._build_client(self.other_admin, self.other_org)

        self.asset = ContentAsset.objects.create(
            organization=self.org,
            external_id="asset-crud-1",
            title="CRUD Test Asset",
            state="draft",
        )

    def _assign_role(self, user, org, role_code):
        role = Role.objects.get(code=role_code)
        UserOrganizationRole.objects.create(user=user, organization=org, role=role)

    def _build_client(self, user, org):
        session = AuthSession.objects.create(
            session_key=AuthSession.new_session_key(),
            user=user,
            organization=org,
            last_activity_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=2),
        )
        client = APIClient()
        client.credentials(HTTP_X_SESSION_KEY=session.session_key)
        return client

    # ---- Asset delete ----

    def test_delete_asset(self):
        asset = ContentAsset.objects.create(
            organization=self.org, external_id="del-asset", title="Delete Me"
        )
        resp = self.admin_client.delete(f"/api/v1/content/assets/{asset.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(ContentAsset.objects.filter(id=asset.id).exists())

    def test_full_update_asset(self):
        resp = self.admin_client.put(
            f"/api/v1/content/assets/{self.asset.id}/",
            {
                "external_id": "asset-crud-1",
                "title": "CRUD Updated Asset",
                "creator": "Curator",
                "period": "Modern",
                "style": "Documentary",
                "medium": "Digital",
                "size": "1080p",
                "source": "Archive",
                "copyright_status": "licensed",
                "tags": ["a", "b"],
                "allow_download": True,
                "allow_share": False,
                "storage_path": "content/crud_updated_asset.png",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["title"], "CRUD Updated Asset")

    def test_delete_asset_forbidden_for_member(self):
        resp = self.member_client.delete(f"/api/v1/content/assets/{self.asset.id}/")
        self.assertEqual(resp.status_code, 403)

    # ---- Chapters CRUD ----

    def test_update_chapter(self):
        chapter = ContentChapter.objects.create(
            organization=self.org,
            asset=self.asset,
            title="Old Chapter",
            order_index=0,
        )
        resp = self.admin_client.patch(
            f"/api/v1/content/chapters/{chapter.id}/",
            {"title": "New Chapter"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["title"], "New Chapter")

    def test_delete_chapter(self):
        chapter = ContentChapter.objects.create(
            organization=self.org,
            asset=self.asset,
            title="Del Chapter",
            order_index=1,
        )
        resp = self.admin_client.delete(f"/api/v1/content/chapters/{chapter.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(ContentChapter.objects.filter(id=chapter.id).exists())

    def test_full_update_chapter(self):
        chapter = ContentChapter.objects.create(
            organization=self.org,
            asset=self.asset,
            title="Full Old Chapter",
            order_index=10,
        )
        resp = self.admin_client.put(
            f"/api/v1/content/chapters/{chapter.id}/",
            {
                "asset": self.asset.id,
                "title": "Full New Chapter",
                "order_index": 11,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["title"], "Full New Chapter")

    def test_chapter_cross_tenant_isolation(self):
        chapter = ContentChapter.objects.create(
            organization=self.org,
            asset=self.asset,
            title="Iso Chapter",
            order_index=2,
        )
        resp = self.other_admin_client.get(f"/api/v1/content/chapters/{chapter.id}/")
        self.assertEqual(resp.status_code, 404)

    def test_member_cannot_create_chapter(self):
        resp = self.member_client.post(
            "/api/v1/content/chapters/",
            {"asset": self.asset.id, "title": "Hack Chapter", "order_index": 99},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    # ---- Chapter ACL CRUD ----

    def test_list_chapter_acl(self):
        chapter = ContentChapter.objects.create(
            organization=self.org, asset=self.asset, title="ACL List Ch", order_index=3
        )
        ContentChapterACL.objects.create(
            organization=self.org,
            chapter=chapter,
            principal_type="role",
            principal_value="member",
        )
        resp = self.admin_client.get("/api/v1/content/chapter-acl/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_retrieve_chapter_acl(self):
        chapter = ContentChapter.objects.create(
            organization=self.org, asset=self.asset, title="ACL Ret Ch", order_index=4
        )
        acl = ContentChapterACL.objects.create(
            organization=self.org,
            chapter=chapter,
            principal_type="role",
            principal_value="member",
        )
        resp = self.admin_client.get(f"/api/v1/content/chapter-acl/{acl.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["principal_type"], "role")

    def test_update_chapter_acl(self):
        chapter = ContentChapter.objects.create(
            organization=self.org, asset=self.asset, title="ACL Upd Ch", order_index=5
        )
        acl = ContentChapterACL.objects.create(
            organization=self.org,
            chapter=chapter,
            principal_type="role",
            principal_value="member",
            can_view=True,
        )
        resp = self.admin_client.patch(
            f"/api/v1/content/chapter-acl/{acl.id}/",
            {"can_view": False},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["can_view"])

    def test_delete_chapter_acl(self):
        chapter = ContentChapter.objects.create(
            organization=self.org, asset=self.asset, title="ACL Del Ch", order_index=6
        )
        acl = ContentChapterACL.objects.create(
            organization=self.org,
            chapter=chapter,
            principal_type="role",
            principal_value="member",
        )
        resp = self.admin_client.delete(f"/api/v1/content/chapter-acl/{acl.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(ContentChapterACL.objects.filter(id=acl.id).exists())

    def test_full_update_chapter_acl(self):
        chapter = ContentChapter.objects.create(
            organization=self.org, asset=self.asset, title="ACL Full Ch", order_index=7
        )
        acl = ContentChapterACL.objects.create(
            organization=self.org,
            chapter=chapter,
            principal_type="role",
            principal_value="member",
            can_view=True,
        )
        resp = self.admin_client.put(
            f"/api/v1/content/chapter-acl/{acl.id}/",
            {
                "chapter": chapter.id,
                "principal_type": "role",
                "principal_value": "member",
                "can_view": False,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["can_view"])

    def test_member_cannot_manage_chapter_acl(self):
        resp = self.member_client.get("/api/v1/content/chapter-acl/")
        self.assertEqual(resp.status_code, 403)

    # ---- Entitlements CRUD ----

    def test_list_entitlements(self):
        ContentEntitlement.objects.create(
            organization=self.org,
            user=self.member,
            asset=self.asset,
            source="subscription",
            is_active=True,
            granted_by=self.admin,
        )
        resp = self.admin_client.get("/api/v1/content/entitlements/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_retrieve_entitlement(self):
        ent = ContentEntitlement.objects.create(
            organization=self.org,
            user=self.member,
            asset=self.asset,
            source="subscription",
            is_active=True,
            granted_by=self.admin,
        )
        resp = self.admin_client.get(f"/api/v1/content/entitlements/{ent.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["source"], "subscription")
        self.assertTrue(resp.json()["is_active"])

    def test_update_entitlement(self):
        ent = ContentEntitlement.objects.create(
            organization=self.org,
            user=self.member,
            asset=self.asset,
            source="subscription",
            is_active=True,
            granted_by=self.admin,
        )
        resp = self.admin_client.patch(
            f"/api/v1/content/entitlements/{ent.id}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["is_active"])

    def test_delete_entitlement(self):
        ent = ContentEntitlement.objects.create(
            organization=self.org,
            user=self.member,
            asset=self.asset,
            source="subscription",
            is_active=True,
            granted_by=self.admin,
        )
        resp = self.admin_client.delete(f"/api/v1/content/entitlements/{ent.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(ContentEntitlement.objects.filter(id=ent.id).exists())

    def test_full_update_entitlement(self):
        ent = ContentEntitlement.objects.create(
            organization=self.org,
            user=self.member,
            asset=self.asset,
            source="subscription",
            is_active=True,
            granted_by=self.admin,
        )
        resp = self.admin_client.put(
            f"/api/v1/content/entitlements/{ent.id}/",
            {
                "user": self.member.id,
                "asset": self.asset.id,
                "is_active": False,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["is_active"])

    def test_entitlement_cross_tenant_isolation(self):
        ent = ContentEntitlement.objects.create(
            organization=self.org,
            user=self.member,
            asset=self.asset,
            source="subscription",
            is_active=True,
            granted_by=self.admin,
        )
        resp = self.other_admin_client.get(f"/api/v1/content/entitlements/{ent.id}/")
        self.assertEqual(resp.status_code, 404)

    # ---- Redeem Codes list ----

    def test_list_redeem_codes(self):
        ContentRedeemCode.objects.create(
            organization=self.org,
            asset=self.asset,
            code_hash=hashlib.sha256(b"testcode1234").hexdigest(),
            code_last4="1234",
            expires_at=timezone.now() + timedelta(days=90),
            created_by=self.admin,
        )
        resp = self.admin_client.get("/api/v1/content/redeem-codes/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_redeem_codes_list_forbidden_for_member(self):
        resp = self.member_client.get("/api/v1/content/redeem-codes/")
        self.assertEqual(resp.status_code, 403)

    # ---- Download Tokens list ----

    def test_list_download_tokens(self):
        published_asset = ContentAsset.objects.create(
            organization=self.org,
            external_id="dl-tok-asset",
            title="DL Token Asset",
            state="published",
            allow_download=True,
        )
        ContentDownloadToken.objects.create(
            organization=self.org,
            user=self.member,
            asset=published_asset,
            token_hash=hashlib.sha256(b"tok12345678").hexdigest(),
            token_hint="tok1...5678",
            purpose="download",
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        resp = self.admin_client.get("/api/v1/content/download-tokens/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)
