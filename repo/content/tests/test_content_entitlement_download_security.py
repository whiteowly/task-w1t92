from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from common.constants import RoleCode
from content.models import (
    AssetState,
    ContentAsset,
    ContentArtifact,
    ContentChapter,
    ContentDownloadRequestLog,
    ContentDownloadToken,
    ContentEntitlement,
    ContentRedeemCode,
)
from iam.models import AuthSession, Role, UserOrganizationRole
from tenancy.models import Organization

User = get_user_model()


class ContentEntitlementDownloadSecurityTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Org A", slug="org-a", timezone="UTC"
        )

        self.admin = User.objects.create_user(
            username="content-sec-admin", password="ValidPass123!"
        )
        self.member = User.objects.create_user(
            username="content-sec-member", password="ValidPass123!"
        )

        self._assign_role(self.admin, self.org, RoleCode.ADMINISTRATOR.value)
        self._assign_role(self.member, self.org, RoleCode.MEMBER.value)

        self.admin_client = self._build_client(self.admin, self.org)
        self.member_client = self._build_client(self.member, self.org)

        media_root = Path(settings.MEDIA_ROOT)
        media_root.mkdir(parents=True, exist_ok=True)
        self.sample_image_rel = "content/sample_asset.png"
        sample_image_abs = media_root / self.sample_image_rel
        sample_image_abs.parent.mkdir(parents=True, exist_ok=True)

        image = Image.new("RGB", (240, 140), color=(200, 200, 200))
        image.save(sample_image_abs)

        asset_resp = self.admin_client.post(
            "/api/v1/content/assets/",
            {
                "external_id": "asset-sec-1",
                "title": "Secured Asset",
                "creator": "Creator",
                "allow_download": True,
                "allow_share": False,
                "storage_path": self.sample_image_rel,
                "tags": ["secure"],
            },
            format="json",
        )
        self.assertEqual(asset_resp.status_code, 201)
        self.asset_id = asset_resp.json()["id"]
        self.admin_client.post(
            f"/api/v1/content/assets/{self.asset_id}/publish/", {}, format="json"
        )

        chapter_resp = self.admin_client.post(
            "/api/v1/content/chapters/",
            {"asset": self.asset_id, "title": "C1", "order_index": 1},
            format="json",
        )
        self.assertEqual(chapter_resp.status_code, 201)
        chapter_id = chapter_resp.json()["id"]

        acl_resp = self.admin_client.post(
            "/api/v1/content/chapter-acl/",
            {
                "chapter": chapter_id,
                "principal_type": "user",
                "principal_value": str(self.member.id),
                "can_view": True,
            },
            format="json",
        )
        self.assertEqual(acl_resp.status_code, 201)

    def _assign_role(self, user, organization, role_code):
        role = Role.objects.get(code=role_code)
        UserOrganizationRole.objects.create(
            user=user, organization=organization, role=role
        )

    def _build_client(self, user, organization):
        session = AuthSession.objects.create(
            session_key=AuthSession.new_session_key(),
            user=user,
            organization=organization,
            last_activity_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=2),
        )
        client = APIClient()
        client.credentials(HTTP_X_SESSION_KEY=session.session_key)
        return client

    def _create_code(self):
        code_resp = self.admin_client.post(
            "/api/v1/content/redeem-codes/",
            {"asset": self.asset_id},
            format="json",
        )
        self.assertEqual(code_resp.status_code, 201)
        return code_resp.json()["code"], code_resp.json()["id"]

    def test_redeem_code_single_use_and_expiry_enforced(self):
        code, code_id = self._create_code()

        first_redeem = self.member_client.post(
            "/api/v1/content/redeem-codes/redeem/",
            {"code": code},
            format="json",
        )
        self.assertEqual(first_redeem.status_code, 200)

        second_redeem = self.member_client.post(
            "/api/v1/content/redeem-codes/redeem/",
            {"code": code},
            format="json",
        )
        self.assertEqual(second_redeem.status_code, 400)
        self.assertEqual(
            second_redeem.json()["error"]["code"], "content.redeem_code.used"
        )

        code2, code2_id = self._create_code()
        ContentRedeemCode.objects.filter(id=code2_id).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        expired_redeem = self.member_client.post(
            "/api/v1/content/redeem-codes/redeem/",
            {"code": code2},
            format="json",
        )
        self.assertEqual(expired_redeem.status_code, 400)
        self.assertEqual(
            expired_redeem.json()["error"]["code"], "content.redeem_code.expired"
        )

    def test_download_token_expiry_enforced(self):
        code, _ = self._create_code()
        redeem = self.member_client.post(
            "/api/v1/content/redeem-codes/redeem/",
            {"code": code},
            format="json",
        )
        self.assertEqual(redeem.status_code, 200)

        token_resp = self.member_client.post(
            "/api/v1/content/download-tokens/",
            {"asset": self.asset_id, "purpose": "download"},
            format="json",
        )
        self.assertEqual(token_resp.status_code, 201)
        token_value = token_resp.json()["token"]

        ContentDownloadToken.objects.update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        expired_download = self.member_client.get(
            f"/api/v1/content/secured-download/{token_value}/"
        )
        self.assertEqual(expired_download.status_code, 403)
        self.assertEqual(
            expired_download.json()["error"]["code"],
            "content.download_token.expired",
        )
        self.assertTrue(
            ContentDownloadRequestLog.objects.filter(
                organization=self.org,
                user=self.member,
                asset_id=self.asset_id,
                status="token_expired",
            ).exists()
        )

    def test_permission_denial_for_missing_entitlement_and_content_permissions(self):
        no_entitlement_token = self.member_client.post(
            "/api/v1/content/download-tokens/",
            {"asset": self.asset_id, "purpose": "download"},
            format="json",
        )
        self.assertEqual(no_entitlement_token.status_code, 403)
        self.assertEqual(
            no_entitlement_token.json()["error"]["code"],
            "content.entitlement.required",
        )

        self.admin_client.post(
            "/api/v1/content/entitlements/",
            {"user": self.member.id, "asset": self.asset_id, "is_active": True},
            format="json",
        )

        ContentAsset.objects.filter(id=self.asset_id).update(allow_download=False)
        denied_permission = self.member_client.post(
            "/api/v1/content/download-tokens/",
            {"asset": self.asset_id, "purpose": "download"},
            format="json",
        )
        self.assertEqual(denied_permission.status_code, 403)
        self.assertEqual(
            denied_permission.json()["error"]["code"],
            "content.download.permission_denied",
        )

    def test_download_rate_limit_enforced(self):
        self.admin_client.post(
            "/api/v1/content/entitlements/",
            {"user": self.member.id, "asset": self.asset_id, "is_active": True},
            format="json",
        )

        token_resp = self.member_client.post(
            "/api/v1/content/download-tokens/",
            {"asset": self.asset_id, "purpose": "download"},
            format="json",
        )
        self.assertEqual(token_resp.status_code, 201)
        token_value = token_resp.json()["token"]

        now = timezone.now()
        logs = [
            ContentDownloadRequestLog(
                organization=self.org,
                user=self.member,
                asset=ContentAsset.objects.get(id=self.asset_id),
                status="served",
                requested_at=now,
            )
            for _ in range(60)
        ]
        ContentDownloadRequestLog.objects.bulk_create(logs)
        ContentDownloadRequestLog.objects.filter(
            organization=self.org,
            user=self.member,
            asset_id=self.asset_id,
        ).update(requested_at=now)

        rate_limited = self.member_client.get(
            f"/api/v1/content/secured-download/{token_value}/"
        )
        self.assertEqual(rate_limited.status_code, 429)
        self.assertEqual(
            rate_limited.json()["error"]["code"],
            "content.download.rate_limited",
        )
        self.assertEqual(
            ContentDownloadRequestLog.objects.filter(
                organization=self.org,
                user=self.member,
                asset_id=self.asset_id,
            ).count(),
            61,
        )
        self.assertTrue(
            ContentDownloadRequestLog.objects.filter(
                organization=self.org,
                user=self.member,
                asset_id=self.asset_id,
                status="rate_limited",
            ).exists()
        )

    def test_secured_download_success_generates_local_watermarked_artifact(self):
        self.admin_client.post(
            "/api/v1/content/entitlements/",
            {"user": self.member.id, "asset": self.asset_id, "is_active": True},
            format="json",
        )

        token_resp = self.member_client.post(
            "/api/v1/content/download-tokens/",
            {"asset": self.asset_id, "purpose": "download"},
            format="json",
        )
        self.assertEqual(token_resp.status_code, 201)
        token_value = token_resp.json()["token"]

        download_resp = self.member_client.get(
            f"/api/v1/content/secured-download/{token_value}/"
        )
        self.assertEqual(download_resp.status_code, 200)
        self.assertEqual(download_resp["Content-Type"], "image/png")
        self.assertIn("attachment", download_resp["Content-Disposition"])

        artifact = ContentArtifact.objects.get(
            organization=self.org,
            user=self.member,
            asset_id=self.asset_id,
        )
        artifact_path = Path(artifact.artifact_path).resolve()
        export_root = Path(settings.EXPORT_ROOT).resolve()

        self.assertTrue(artifact_path.is_file())
        self.assertTrue(artifact_path.is_relative_to(export_root))
        self.assertEqual(
            artifact_path.parent,
            (export_root / "content_downloads").resolve(),
        )

        source_image = Image.open(
            Path(settings.MEDIA_ROOT) / self.sample_image_rel
        ).convert("RGB")
        artifact_image = Image.open(artifact_path).convert("RGB")
        self.assertEqual(source_image.size, artifact_image.size)
        self.assertNotEqual(
            (Path(settings.MEDIA_ROOT) / self.sample_image_rel).read_bytes(),
            artifact_path.read_bytes(),
        )

        source_has_red = any(
            pixel[0] > pixel[1] and pixel[0] > pixel[2]
            for pixel in source_image.getdata()
        )
        artifact_has_red = any(
            pixel[0] > pixel[1] and pixel[0] > pixel[2]
            for pixel in artifact_image.getdata()
        )
        self.assertFalse(source_has_red)
        self.assertTrue(artifact_has_red)
        self.assertTrue(
            ContentDownloadRequestLog.objects.filter(
                organization=self.org,
                user=self.member,
                asset_id=self.asset_id,
                status="served",
            ).exists()
        )

    def test_download_token_rejected_after_entitlement_revoked(self):
        self.admin_client.post(
            "/api/v1/content/entitlements/",
            {"user": self.member.id, "asset": self.asset_id, "is_active": True},
            format="json",
        )

        token_resp = self.member_client.post(
            "/api/v1/content/download-tokens/",
            {"asset": self.asset_id, "purpose": "download"},
            format="json",
        )
        self.assertEqual(token_resp.status_code, 201)
        token_value = token_resp.json()["token"]

        ContentEntitlement.objects.filter(
            organization=self.org,
            user=self.member,
            asset_id=self.asset_id,
        ).update(is_active=False)

        download_resp = self.member_client.get(
            f"/api/v1/content/secured-download/{token_value}/"
        )
        self.assertEqual(download_resp.status_code, 403)
        self.assertEqual(
            download_resp.json()["error"]["code"],
            "content.entitlement.required",
        )

    def test_download_token_rejected_after_asset_unpublished(self):
        self.admin_client.post(
            "/api/v1/content/entitlements/",
            {"user": self.member.id, "asset": self.asset_id, "is_active": True},
            format="json",
        )

        token_resp = self.member_client.post(
            "/api/v1/content/download-tokens/",
            {"asset": self.asset_id, "purpose": "download"},
            format="json",
        )
        self.assertEqual(token_resp.status_code, 201)
        token_value = token_resp.json()["token"]

        self.admin_client.post(
            f"/api/v1/content/assets/{self.asset_id}/unpublish/",
            {},
            format="json",
        )

        download_resp = self.member_client.get(
            f"/api/v1/content/secured-download/{token_value}/"
        )
        self.assertEqual(download_resp.status_code, 403)
        self.assertEqual(
            download_resp.json()["error"]["code"],
            "content.asset.not_published",
        )
