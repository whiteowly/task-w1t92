from django.contrib import admin

from content.models import (
    ContentAsset,
    ContentAssetVersionLog,
    ContentArtifact,
    ContentDownloadRequestLog,
    ContentDownloadToken,
    ContentEntitlement,
    ContentChapter,
    ContentChapterACL,
    ContentRedeemCode,
)

admin.site.register(ContentAsset)
admin.site.register(ContentChapter)
admin.site.register(ContentChapterACL)
admin.site.register(ContentAssetVersionLog)
admin.site.register(ContentEntitlement)
admin.site.register(ContentRedeemCode)
admin.site.register(ContentDownloadToken)
admin.site.register(ContentDownloadRequestLog)
admin.site.register(ContentArtifact)
