import csv

from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from common.constants import RoleCode
from common.mixins import OrganizationScopedViewSetMixin
from common.permissions import IsOrganizationMember
from content.models import (
    AssetState,
    ChapterACLPrincipal,
    ContentAsset,
    ContentAssetVersionLog,
    ContentDownloadToken,
    ContentEntitlement,
    ContentChapter,
    ContentChapterACL,
    ContentRedeemCode,
    DownloadTokenPurpose,
)
from content.serializers import (
    AssetImportCSVSerializer,
    AssetImportJSONSerializer,
    ContentDownloadTokenCreateSerializer,
    ContentDownloadTokenSerializer,
    ContentEntitlementSerializer,
    ContentRedeemCodeCreateSerializer,
    ContentRedeemCodeRedeemSerializer,
    ContentRedeemCodeSerializer,
    AssetPublishSerializer,
    ContentAssetSerializer,
    ContentAssetVersionLogSerializer,
    ContentChapterACLSerializer,
    ContentChapterSerializer,
)
from content.services import (
    IMPORT_FIELDS,
    bulk_import_items,
    create_redeem_code,
    create_asset,
    generate_secured_download_artifact,
    grant_subscription_entitlement,
    issue_download_token,
    parse_csv_rows,
    redeem_code,
    set_asset_state,
    update_asset,
)
from observability.services import log_audit_event

MANAGER_ROLES = {RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value}


class ActionRolePermission(BasePermission):
    message = "Insufficient role for this action."

    def has_permission(self, request, view):
        action_roles = getattr(view, "action_roles", {})
        required = action_roles.get(getattr(view, "action", None))
        if not required:
            required = getattr(view, "required_roles", None)
        if not required:
            return True
        role_codes = set(getattr(request, "role_codes", []))
        return bool(role_codes.intersection(set(required)))


class ContentAssetViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ContentAsset.objects.all().order_by("-updated_at")
    serializer_class = ContentAssetSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [role.value for role in RoleCode],
        "retrieve": [role.value for role in RoleCode],
        "create": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "update": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "partial_update": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "destroy": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "publish": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "unpublish": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "version_logs": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "import_json": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "import_csv": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "export": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        role_codes = set(getattr(self.request, "role_codes", []))
        if role_codes.intersection(MANAGER_ROLES):
            return queryset

        user_id = str(self.request.user.id)
        role_values = list(role_codes)
        return (
            queryset.filter(
                state=AssetState.PUBLISHED,
                entitlements__organization=self.request.organization,
                entitlements__user=self.request.user,
                entitlements__is_active=True,
                chapters__acl_entries__can_view=True,
            )
            .filter(
                Q(
                    chapters__acl_entries__principal_type=ChapterACLPrincipal.USER,
                    chapters__acl_entries__principal_value=user_id,
                )
                | (
                    Q(chapters__acl_entries__principal_type=ChapterACLPrincipal.ROLE)
                    & Q(chapters__acl_entries__principal_value__in=role_values)
                )
            )
            .distinct()
        )

    def perform_create(self, serializer):
        asset = create_asset(
            organization=self.get_organization(),
            actor=self.request.user,
            payload=serializer.validated_data,
            request=self.request,
        )
        serializer.instance = asset

    def perform_update(self, serializer):
        asset = update_asset(
            asset=self.get_object(),
            actor=self.request.user,
            payload=serializer.validated_data,
            request=self.request,
        )
        serializer.instance = asset

    def perform_destroy(self, instance):
        asset_id = instance.id
        organization = instance.organization
        super().perform_destroy(instance)
        log_audit_event(
            action="content.asset.delete",
            organization=organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="content_asset",
            resource_id=str(asset_id),
        )

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        serializer = AssetPublishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asset = set_asset_state(
            asset=self.get_object(),
            actor=request.user,
            to_state=AssetState.PUBLISHED,
            request=request,
        )
        return Response(ContentAssetSerializer(asset).data)

    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        serializer = AssetPublishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asset = set_asset_state(
            asset=self.get_object(),
            actor=request.user,
            to_state=AssetState.DRAFT,
            request=request,
        )
        return Response(ContentAssetSerializer(asset).data)

    @action(detail=True, methods=["get"])
    def version_logs(self, request, pk=None):
        asset = self.get_object()
        logs = ContentAssetVersionLog.objects.filter(
            organization=request.organization,
            asset=asset,
        ).order_by("-version")
        return Response(ContentAssetVersionLogSerializer(logs, many=True).data)

    @action(detail=False, methods=["post"], url_path="import/json")
    def import_json(self, request):
        serializer = AssetImportJSONSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        created = bulk_import_items(
            organization=request.organization,
            actor=request.user,
            items=serializer.validated_data["items"],
            request=request,
            source="json",
        )
        return Response({"created_count": len(created)}, status=201)

    @action(detail=False, methods=["post"], url_path="import/csv")
    def import_csv(self, request):
        serializer = AssetImportCSVSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("file") is not None:
            csv_bytes = serializer.validated_data["file"].read()
            csv_text = csv_bytes.decode("utf-8")
        else:
            csv_text = serializer.validated_data["csv_content"]

        rows = parse_csv_rows(csv_text)
        created = bulk_import_items(
            organization=request.organization,
            actor=request.user,
            items=rows,
            request=request,
            source="csv",
        )
        return Response({"created_count": len(created)}, status=201)

    @action(detail=False, methods=["get"])
    def export(self, request):
        export_format = request.query_params.get("format", "json")
        assets = self.get_queryset().order_by("id")

        if export_format == "csv":
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = "attachment; filename=content_assets.csv"
            writer = csv.DictWriter(response, fieldnames=IMPORT_FIELDS)
            writer.writeheader()
            for asset in assets:
                writer.writerow(
                    {
                        "external_id": asset.external_id,
                        "title": asset.title,
                        "creator": asset.creator,
                        "period": asset.period,
                        "style": asset.style,
                        "medium": asset.medium,
                        "size": asset.size,
                        "source": asset.source,
                        "copyright_status": asset.copyright_status,
                        "tags": "|".join(asset.tags or []),
                        "state": asset.state,
                        "allow_download": str(asset.allow_download).lower(),
                        "allow_share": str(asset.allow_share).lower(),
                        "storage_path": asset.storage_path,
                    }
                )
            log_audit_event(
                action="content.asset.export.csv",
                organization=request.organization,
                actor_user=request.user,
                request=request,
                resource_type="content_asset",
                resource_id="bulk",
                metadata={"export_count": assets.count()},
            )
            return response

        payload = ContentAssetSerializer(assets, many=True).data
        log_audit_event(
            action="content.asset.export.json",
            organization=request.organization,
            actor_user=request.user,
            request=request,
            resource_type="content_asset",
            resource_id="bulk",
            metadata={"export_count": len(payload)},
        )
        return Response(payload)


class ContentChapterViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ContentChapter.objects.select_related("asset").all()
    serializer_class = ContentChapterSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [role.value for role in RoleCode],
        "retrieve": [role.value for role in RoleCode],
        "create": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "update": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "partial_update": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "destroy": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        role_codes = set(getattr(self.request, "role_codes", []))
        if role_codes.intersection(MANAGER_ROLES):
            return queryset

        user_id = str(self.request.user.id)
        role_values = list(role_codes)
        return (
            queryset.filter(
                asset__state=AssetState.PUBLISHED,
                asset__entitlements__organization=self.request.organization,
                asset__entitlements__user=self.request.user,
                asset__entitlements__is_active=True,
                acl_entries__can_view=True,
            )
            .filter(
                (
                    Q(
                        acl_entries__principal_type=ChapterACLPrincipal.USER,
                        acl_entries__principal_value=user_id,
                    )
                )
                | (
                    Q(acl_entries__principal_type=ChapterACLPrincipal.ROLE)
                    & Q(acl_entries__principal_value__in=role_values)
                )
            )
            .distinct()
        )

    def perform_create(self, serializer):
        chapter = serializer.save(organization=self.get_organization())
        log_audit_event(
            action="content.chapter.create",
            organization=chapter.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="content_chapter",
            resource_id=str(chapter.id),
            metadata={"asset_id": chapter.asset_id},
        )

    def perform_update(self, serializer):
        chapter = serializer.save()
        log_audit_event(
            action="content.chapter.update",
            organization=chapter.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="content_chapter",
            resource_id=str(chapter.id),
        )

    def perform_destroy(self, instance):
        chapter_id = instance.id
        organization = instance.organization
        super().perform_destroy(instance)
        log_audit_event(
            action="content.chapter.delete",
            organization=organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="content_chapter",
            resource_id=str(chapter_id),
        )


class ContentChapterACLViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ContentChapterACL.objects.select_related("chapter").all()
    serializer_class = ContentChapterACLSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "retrieve": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "create": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "update": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "partial_update": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "destroy": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
    }

    def perform_create(self, serializer):
        acl = serializer.save(organization=self.get_organization())
        log_audit_event(
            action="content.chapter_acl.create",
            organization=acl.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="content_chapter_acl",
            resource_id=str(acl.id),
            metadata={
                "chapter_id": acl.chapter_id,
                "principal_type": acl.principal_type,
                "principal_value": acl.principal_value,
            },
        )

    def perform_update(self, serializer):
        acl = serializer.save()
        log_audit_event(
            action="content.chapter_acl.update",
            organization=acl.organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="content_chapter_acl",
            resource_id=str(acl.id),
        )

    def perform_destroy(self, instance):
        acl_id = instance.id
        organization = instance.organization
        super().perform_destroy(instance)
        log_audit_event(
            action="content.chapter_acl.delete",
            organization=organization,
            actor_user=self.request.user,
            request=self.request,
            resource_type="content_chapter_acl",
            resource_id=str(acl_id),
        )


class ContentEntitlementViewSet(OrganizationScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ContentEntitlement.objects.select_related("asset", "user").all()
    serializer_class = ContentEntitlementSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "retrieve": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "create": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "update": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "partial_update": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "destroy": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
    }

    def perform_create(self, serializer):
        entitlement = grant_subscription_entitlement(
            organization=self.get_organization(),
            user=serializer.validated_data["user"],
            asset=serializer.validated_data["asset"],
            actor=self.request.user,
            request=self.request,
        )
        serializer.instance = entitlement


class ContentRedeemCodeViewSet(
    OrganizationScopedViewSetMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = ContentRedeemCode.objects.select_related("asset", "redeemed_by").all()
    serializer_class = ContentRedeemCodeSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "create": [RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value],
        "redeem": [role.value for role in RoleCode],
    }

    def get_serializer_class(self):
        if self.action == "create":
            return ContentRedeemCodeCreateSerializer
        if self.action == "redeem":
            return ContentRedeemCodeRedeemSerializer
        return super().get_serializer_class()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code, code_plain = create_redeem_code(
            organization=request.organization,
            asset=serializer.validated_data["asset"],
            actor=request.user,
            request=request,
            expires_at=serializer.validated_data.get("expires_at"),
        )
        return Response(
            {
                "id": code.id,
                "asset": code.asset_id,
                "code": code_plain,
                "code_last4": code.code_last4,
                "expires_at": code.expires_at,
            },
            status=201,
        )

    @action(detail=False, methods=["post"])
    def redeem(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entitlement = redeem_code(
            organization=request.organization,
            user=request.user,
            code_value=serializer.validated_data["code"],
            request=request,
        )
        return Response(
            {
                "entitlement_id": entitlement.id,
                "asset_id": entitlement.asset_id,
                "source": entitlement.source,
            }
        )


class ContentDownloadTokenViewSet(
    OrganizationScopedViewSetMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = ContentDownloadToken.objects.select_related("asset", "user").all()
    serializer_class = ContentDownloadTokenSerializer
    permission_classes = [IsOrganizationMember, ActionRolePermission]
    action_roles = {
        "list": [role.value for role in RoleCode],
        "create": [role.value for role in RoleCode],
    }

    def get_serializer_class(self):
        if self.action == "create":
            return ContentDownloadTokenCreateSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        queryset = super().get_queryset()
        role_codes = set(getattr(self.request, "role_codes", []))
        if role_codes.intersection(MANAGER_ROLES):
            return queryset
        return queryset.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token, token_plain = issue_download_token(
            organization=request.organization,
            user=request.user,
            asset=serializer.validated_data["asset"],
            purpose=serializer.validated_data.get(
                "purpose", DownloadTokenPurpose.DOWNLOAD
            ),
            role_codes=set(getattr(request, "role_codes", [])),
            request=request,
        )
        return Response(
            {
                "token": token_plain,
                "token_hint": token.token_hint,
                "expires_at": token.expires_at,
                "purpose": token.purpose,
                "asset_id": token.asset_id,
            },
            status=201,
        )


class SecuredContentDownloadView(APIView):
    permission_classes = [IsOrganizationMember]

    def get(self, request, token: str):
        artifact = generate_secured_download_artifact(
            organization=request.organization,
            user=request.user,
            token_value=token,
            request=request,
        )

        try:
            file_handle = open(artifact.artifact_path, "rb")
        except FileNotFoundError as exc:
            raise Http404("Artifact not found") from exc

        response = FileResponse(file_handle, content_type=artifact.mime_type)
        response["Content-Disposition"] = (
            f'attachment; filename="{artifact.asset.external_id}_{artifact.id}"'
        )
        return response
