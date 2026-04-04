from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from common.constants import RoleCode
from content.models import (
    AssetState,
    ContentAsset,
    ContentAssetVersionLog,
    ContentChapter,
)
from iam.models import AuthSession, Role, UserOrganizationRole
from observability.models import AuditLog
from tenancy.models import Organization

User = get_user_model()


class ContentApiTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(
            name="Org A", slug="org-a", timezone="UTC"
        )
        self.org_b = Organization.objects.create(
            name="Org B", slug="org-b", timezone="UTC"
        )

        self.admin_a = User.objects.create_user(
            username="content-admin-a", password="ValidPass123!"
        )
        self.member_a = User.objects.create_user(
            username="content-member-a", password="ValidPass123!"
        )
        self.member_b = User.objects.create_user(
            username="content-member-b", password="ValidPass123!"
        )
        self.admin_b = User.objects.create_user(
            username="content-admin-b", password="ValidPass123!"
        )

        self._assign_role(self.admin_a, self.org_a, RoleCode.ADMINISTRATOR.value)
        self._assign_role(self.member_a, self.org_a, RoleCode.MEMBER.value)
        self._assign_role(self.member_b, self.org_a, RoleCode.MEMBER.value)
        self._assign_role(self.admin_b, self.org_b, RoleCode.ADMINISTRATOR.value)

        self.admin_client = self._build_client(self.admin_a, self.org_a)
        self.member_client = self._build_client(self.member_a, self.org_a)

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

    def _create_asset(self, external_id="asset-001"):
        response = self.admin_client.post(
            "/api/v1/content/assets/",
            {
                "external_id": external_id,
                "title": "Mona Lisa",
                "creator": "Da Vinci",
                "period": "Renaissance",
                "style": "Portrait",
                "medium": "Oil",
                "size": "77x53 cm",
                "source": "Louvre",
                "copyright_status": "public_domain",
                "tags": ["renaissance", "portrait"],
                "allow_download": True,
                "allow_share": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_versioning_monotonic_and_publish_state_flow(self):
        created = self._create_asset("asset-ver-1")
        asset_id = created["id"]
        self.assertEqual(created["version"], 1)
        self.assertEqual(created["state"], AssetState.DRAFT)

        updated = self.admin_client.patch(
            f"/api/v1/content/assets/{asset_id}/",
            {"title": "Mona Lisa Updated"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["version"], 2)

        published = self.admin_client.post(
            f"/api/v1/content/assets/{asset_id}/publish/",
            {},
            format="json",
        )
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.json()["state"], AssetState.PUBLISHED)
        self.assertEqual(published.json()["version"], 3)

        unpublished = self.admin_client.post(
            f"/api/v1/content/assets/{asset_id}/unpublish/",
            {},
            format="json",
        )
        self.assertEqual(unpublished.status_code, 200)
        self.assertEqual(unpublished.json()["state"], AssetState.DRAFT)
        self.assertEqual(unpublished.json()["version"], 4)

        logs = ContentAssetVersionLog.objects.filter(asset_id=asset_id).order_by(
            "version"
        )
        self.assertEqual(list(logs.values_list("version", flat=True)), [1, 2, 3, 4])

        audit_actions = set(
            AuditLog.objects.filter(
                resource_type="content_asset", resource_id=str(asset_id)
            ).values_list("action", flat=True)
        )
        self.assertIn("content.asset.create", audit_actions)
        self.assertIn("content.asset.update", audit_actions)
        self.assertIn("content.asset.publish", audit_actions)

    def test_bulk_import_duplicate_detection_and_validation_failure(self):
        self._create_asset("dup-existing")

        import_resp = self.admin_client.post(
            "/api/v1/content/assets/import/json/",
            {
                "items": [
                    {
                        "external_id": "dup-existing",
                        "title": "Existing",
                        "tags": ["a"],
                    },
                    {
                        "external_id": "dup-payload",
                        "title": "First",
                        "tags": ["b"],
                    },
                    {
                        "external_id": "dup-payload",
                        "title": "Second",
                        "tags": ["c"],
                    },
                    {
                        "title": "Missing external id",
                        "tags": ["d"],
                    },
                ]
            },
            format="json",
        )
        self.assertEqual(import_resp.status_code, 400)
        self.assertEqual(
            import_resp.json()["error"]["code"], "content.import_validation_failed"
        )

        csv_bad_schema = self.admin_client.post(
            "/api/v1/content/assets/import/csv/",
            {
                "csv_content": "external_id,title\nA-1,Title\n",
            },
            format="json",
        )
        self.assertEqual(csv_bad_schema.status_code, 400)
        self.assertEqual(
            csv_bad_schema.json()["error"]["code"], "content.import_invalid_schema"
        )

    def test_chapter_acl_scoping_and_tenant_isolation(self):
        created = self._create_asset("asset-acl-1")
        asset_id = created["id"]
        self.admin_client.post(
            f"/api/v1/content/assets/{asset_id}/publish/", {}, format="json"
        )

        hidden_created = self._create_asset("asset-hidden-1")
        hidden_asset_id = hidden_created["id"]
        self.admin_client.post(
            f"/api/v1/content/assets/{hidden_asset_id}/publish/", {}, format="json"
        )

        chapter1 = self.admin_client.post(
            "/api/v1/content/chapters/",
            {"asset": asset_id, "title": "Chapter 1", "order_index": 1},
            format="json",
        )
        self.assertEqual(chapter1.status_code, 201)
        chapter1_id = chapter1.json()["id"]

        chapter2 = self.admin_client.post(
            "/api/v1/content/chapters/",
            {"asset": asset_id, "title": "Chapter 2", "order_index": 2},
            format="json",
        )
        self.assertEqual(chapter2.status_code, 201)

        hidden_chapter = self.admin_client.post(
            "/api/v1/content/chapters/",
            {
                "asset": hidden_asset_id,
                "title": "Hidden Chapter",
                "order_index": 1,
            },
            format="json",
        )
        self.assertEqual(hidden_chapter.status_code, 201)
        hidden_chapter_id = hidden_chapter.json()["id"]

        acl_resp = self.admin_client.post(
            "/api/v1/content/chapter-acl/",
            {
                "chapter": chapter1_id,
                "principal_type": "user",
                "principal_value": str(self.member_a.id),
                "can_view": True,
            },
            format="json",
        )
        self.assertEqual(acl_resp.status_code, 201)

        hidden_acl_resp = self.admin_client.post(
            "/api/v1/content/chapter-acl/",
            {
                "chapter": hidden_chapter_id,
                "principal_type": "user",
                "principal_value": str(self.member_b.id),
                "can_view": True,
            },
            format="json",
        )
        self.assertEqual(hidden_acl_resp.status_code, 201)

        no_entitlement_assets = self.member_client.get("/api/v1/content/assets/")
        self.assertEqual(no_entitlement_assets.status_code, 200)
        self.assertEqual(no_entitlement_assets.json(), [])

        no_entitlement_asset_detail = self.member_client.get(
            f"/api/v1/content/assets/{asset_id}/"
        )
        self.assertEqual(no_entitlement_asset_detail.status_code, 404)

        no_entitlement_chapters = self.member_client.get("/api/v1/content/chapters/")
        self.assertEqual(no_entitlement_chapters.status_code, 200)
        self.assertEqual(no_entitlement_chapters.json(), [])

        no_entitlement_chapter_detail = self.member_client.get(
            f"/api/v1/content/chapters/{chapter1_id}/"
        )
        self.assertEqual(no_entitlement_chapter_detail.status_code, 404)

        entitlement_resp = self.admin_client.post(
            "/api/v1/content/entitlements/",
            {
                "user": self.member_a.id,
                "asset": asset_id,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(entitlement_resp.status_code, 201)

        member_assets = self.member_client.get("/api/v1/content/assets/")
        self.assertEqual(member_assets.status_code, 200)
        member_asset_ids = {entry["id"] for entry in member_assets.json()}
        self.assertEqual(member_asset_ids, {asset_id})

        hidden_asset_detail = self.member_client.get(
            f"/api/v1/content/assets/{hidden_asset_id}/"
        )
        self.assertEqual(hidden_asset_detail.status_code, 404)

        member_chapters = self.member_client.get("/api/v1/content/chapters/")
        self.assertEqual(member_chapters.status_code, 200)
        returned_ids = {entry["id"] for entry in member_chapters.json()}
        self.assertEqual(returned_ids, {chapter1_id})

        org_b_asset = ContentAsset.objects.create(
            organization=self.org_b,
            external_id="org-b-asset",
            title="Other tenant",
            state=AssetState.PUBLISHED,
            version=1,
        )
        org_b_chapter = ContentChapter.objects.create(
            organization=self.org_b,
            asset=org_b_asset,
            title="B Chapter",
            order_index=1,
        )

        cross_tenant = self.admin_client.get(
            f"/api/v1/content/chapters/{org_b_chapter.id}/"
        )
        self.assertEqual(cross_tenant.status_code, 404)

    def test_storage_path_managed_on_create_update_and_import(self):
        create_resp = self.admin_client.post(
            "/api/v1/content/assets/",
            {
                "external_id": "asset-storage-1",
                "title": "Storage Path Asset",
                "allow_download": True,
                "storage_path": "content/source_a.png",
                "tags": ["t"],
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)
        asset_id = create_resp.json()["id"]
        self.assertEqual(create_resp.json()["storage_path"], "content/source_a.png")

        update_resp = self.admin_client.patch(
            f"/api/v1/content/assets/{asset_id}/",
            {"storage_path": "content/source_b.png"},
            format="json",
        )
        self.assertEqual(update_resp.status_code, 200)
        self.assertEqual(update_resp.json()["storage_path"], "content/source_b.png")

        import_resp = self.admin_client.post(
            "/api/v1/content/assets/import/json/",
            {
                "items": [
                    {
                        "external_id": "asset-storage-import-1",
                        "title": "Imported Storage",
                        "tags": ["imported"],
                        "storage_path": "content/imported_source.png",
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(import_resp.status_code, 201)
        imported = ContentAsset.objects.get(
            organization=self.org_a,
            external_id="asset-storage-import-1",
        )
        self.assertEqual(imported.storage_path, "content/imported_source.png")

        csv_import_resp = self.admin_client.post(
            "/api/v1/content/assets/import/csv/",
            {
                "csv_content": (
                    "external_id,title,creator,period,style,medium,size,source,copyright_status,tags,state,allow_download,allow_share,storage_path\n"
                    "asset-storage-import-2,Imported CSV,,,,,,,,csv-tag,draft,true,false,content/imported_csv_source.png\n"
                )
            },
            format="json",
        )
        self.assertEqual(csv_import_resp.status_code, 201)
        imported_csv = ContentAsset.objects.get(
            organization=self.org_a,
            external_id="asset-storage-import-2",
        )
        self.assertEqual(imported_csv.storage_path, "content/imported_csv_source.png")

    def test_storage_path_validation_rejects_escape_paths(self):
        create_resp = self.admin_client.post(
            "/api/v1/content/assets/",
            {
                "external_id": "asset-storage-invalid",
                "title": "Invalid",
                "storage_path": "../outside.png",
                "tags": ["bad"],
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 400)

        import_resp = self.admin_client.post(
            "/api/v1/content/assets/import/json/",
            {
                "items": [
                    {
                        "external_id": "asset-storage-import-invalid",
                        "title": "Import Invalid",
                        "tags": ["bad"],
                        "storage_path": "../../escape.png",
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(import_resp.status_code, 400)
        self.assertEqual(
            import_resp.json()["error"]["code"], "content.import_validation_failed"
        )

    def test_member_role_acl_does_not_bypass_asset_entitlement_checks(self):
        org = Organization.objects.create(
            name="Entitlement Org",
            slug="entitlement-org",
            timezone="UTC",
        )
        manager = User.objects.create_user(
            username="content-manager-entitlement",
            password="ValidPass123!",
        )
        member = User.objects.create_user(
            username="content-member-entitlement",
            password="ValidPass123!",
        )
        self._assign_role(manager, org, RoleCode.CLUB_MANAGER.value)
        self._assign_role(member, org, RoleCode.MEMBER.value)

        manager_client = self._build_client(manager, org)
        member_client = self._build_client(member, org)

        asset_resp = manager_client.post(
            "/api/v1/content/assets/",
            {
                "external_id": "asset-entitlement-acl",
                "title": "Entitled Asset",
                "creator": "Curator",
                "period": "Modern",
                "style": "Archive",
                "medium": "Paper",
                "size": "A4",
                "source": "Club Archive",
                "copyright_status": "licensed",
                "tags": ["restricted"],
                "allow_download": False,
                "allow_share": False,
            },
            format="json",
        )
        self.assertEqual(asset_resp.status_code, 201)
        asset_id = asset_resp.json()["id"]

        publish_resp = manager_client.post(
            f"/api/v1/content/assets/{asset_id}/publish/",
            {},
            format="json",
        )
        self.assertEqual(publish_resp.status_code, 200)

        chapter_resp = manager_client.post(
            "/api/v1/content/chapters/",
            {"asset": asset_id, "title": "Member Chapter", "order_index": 1},
            format="json",
        )
        self.assertEqual(chapter_resp.status_code, 201)

        acl_resp = manager_client.post(
            "/api/v1/content/chapter-acl/",
            {
                "chapter": chapter_resp.json()["id"],
                "principal_type": "role",
                "principal_value": RoleCode.MEMBER.value,
                "can_view": True,
            },
            format="json",
        )
        self.assertEqual(acl_resp.status_code, 201)

        list_resp = member_client.get("/api/v1/content/assets/")
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(list_resp.json(), [])

        detail_resp = member_client.get(f"/api/v1/content/assets/{asset_id}/")
        self.assertEqual(detail_resp.status_code, 404)

    def test_asset_version_logs_endpoint_returns_monotonic_history(self):
        created = self._create_asset("asset-version-logs-1")
        asset_id = created["id"]

        publish_resp = self.admin_client.post(
            f"/api/v1/content/assets/{asset_id}/publish/",
            {},
            format="json",
        )
        self.assertEqual(publish_resp.status_code, 200)

        unpublish_resp = self.admin_client.post(
            f"/api/v1/content/assets/{asset_id}/unpublish/",
            {},
            format="json",
        )
        self.assertEqual(unpublish_resp.status_code, 200)

        response = self.admin_client.get(
            f"/api/v1/content/assets/{asset_id}/version_logs/"
        )

        self.assertEqual(response.status_code, 200)
        versions = [entry["version"] for entry in response.json()]
        self.assertEqual(versions, sorted(versions, reverse=True))
        self.assertEqual(list(reversed(versions)), [1, 2, 3])

    def test_asset_version_logs_endpoint_forbids_members(self):
        created = self._create_asset("asset-version-logs-forbidden")

        response = self.member_client.get(
            f"/api/v1/content/assets/{created['id']}/version_logs/"
        )

        self.assertEqual(response.status_code, 403)

    def test_asset_export_returns_json_list_for_managers(self):
        self._create_asset("asset-export-json-1")
        self._create_asset("asset-export-json-2")

        manager = User.objects.create_user(
            username="content-manager-export-json",
            password="ValidPass123!",
        )
        self._assign_role(manager, self.org_a, RoleCode.CLUB_MANAGER.value)
        manager_client = self._build_client(manager, self.org_a)

        response = manager_client.get("/api/v1/content/assets/export/?format=json")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertEqual(
            {item["external_id"] for item in response.json()},
            {"asset-export-json-1", "asset-export-json-2"},
        )

    @override_settings(
        REST_FRAMEWORK={
            "DEFAULT_AUTHENTICATION_CLASSES": [
                "iam.authentication.OrganizationSessionAuthentication",
            ],
            "DEFAULT_PERMISSION_CLASSES": [
                "rest_framework.permissions.IsAuthenticated",
            ],
            "EXCEPTION_HANDLER": "common.exceptions.api_exception_handler",
            "DEFAULT_THROTTLE_CLASSES": [
                "rest_framework.throttling.ScopedRateThrottle",
            ],
            "DEFAULT_THROTTLE_RATES": {
                "auth_login": "30/minute",
                "downloads": "60/minute",
            },
            "URL_FORMAT_OVERRIDE": None,
        }
    )
    def test_asset_export_returns_csv_for_managers(self):
        self._create_asset("asset-export-csv-1")

        manager = User.objects.create_user(
            username="content-manager-export-csv",
            password="ValidPass123!",
        )
        self._assign_role(manager, self.org_a, RoleCode.CLUB_MANAGER.value)
        manager_client = self._build_client(manager, self.org_a)

        response = manager_client.get("/api/v1/content/assets/export/?format=csv")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        self.assertIn("asset-export-csv-1", response.content.decode("utf-8"))

    def test_asset_export_forbids_members(self):
        response = self.member_client.get("/api/v1/content/assets/export/?format=json")

        self.assertEqual(response.status_code, 403)
