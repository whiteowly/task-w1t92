from common.constants import RoleCode

ADMIN_ROLE_CODE = RoleCode.ADMINISTRATOR.value
CLUB_MANAGER_ROLE_CODE = RoleCode.CLUB_MANAGER.value
COUNSELOR_REVIEWER_ROLE_CODE = RoleCode.COUNSELOR_REVIEWER.value
GROUP_LEADER_ROLE_CODE = RoleCode.GROUP_LEADER.value
MEMBER_ROLE_CODE = RoleCode.MEMBER.value

ALL_ROLE_CODES = tuple(role.value for role in RoleCode)
MANAGER_ROLE_CODES = {ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE}
REVIEWER_ROLE_CODES = {COUNSELOR_REVIEWER_ROLE_CODE}

ROLE_PERMISSIONS_MAP = {
    "finance": {
        "CommissionRuleViewSet": {
            "list": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                COUNSELOR_REVIEWER_ROLE_CODE,
            ],
            "retrieve": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                COUNSELOR_REVIEWER_ROLE_CODE,
            ],
            "create": [ADMIN_ROLE_CODE],
            "update": [ADMIN_ROLE_CODE],
            "partial_update": [ADMIN_ROLE_CODE],
            "destroy": [ADMIN_ROLE_CODE],
        },
        "LedgerEntryViewSet": {
            "list": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                COUNSELOR_REVIEWER_ROLE_CODE,
            ],
            "retrieve": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                COUNSELOR_REVIEWER_ROLE_CODE,
            ],
        },
        "SettlementViewSet": {
            "list": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                COUNSELOR_REVIEWER_ROLE_CODE,
                GROUP_LEADER_ROLE_CODE,
            ],
            "retrieve": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                COUNSELOR_REVIEWER_ROLE_CODE,
                GROUP_LEADER_ROLE_CODE,
            ],
            "generate": [ADMIN_ROLE_CODE],
        },
        "WithdrawalBlacklistViewSet": {
            "list": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "retrieve": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "create": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "update": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "partial_update": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "destroy": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
        },
        "WithdrawalRequestViewSet": {
            "list": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                COUNSELOR_REVIEWER_ROLE_CODE,
                GROUP_LEADER_ROLE_CODE,
            ],
            "retrieve": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                COUNSELOR_REVIEWER_ROLE_CODE,
                GROUP_LEADER_ROLE_CODE,
            ],
            "create": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                GROUP_LEADER_ROLE_CODE,
            ],
            "review": [COUNSELOR_REVIEWER_ROLE_CODE],
        },
    },
    "content": {
        "ContentAssetViewSet": {
            "list": list(ALL_ROLE_CODES),
            "retrieve": list(ALL_ROLE_CODES),
            "create": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "update": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "partial_update": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "destroy": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "publish": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "unpublish": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "version_logs": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "import_json": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "import_csv": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "export": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
        },
        "ContentChapterViewSet": {
            "list": list(ALL_ROLE_CODES),
            "retrieve": list(ALL_ROLE_CODES),
            "create": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "update": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "partial_update": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "destroy": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
        },
        "ContentChapterACLViewSet": {
            "list": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "retrieve": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "create": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "update": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "partial_update": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "destroy": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
        },
        "ContentEntitlementViewSet": {
            "list": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "retrieve": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "create": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "update": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "partial_update": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "destroy": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
        },
        "ContentRedeemCodeViewSet": {
            "list": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "create": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "redeem": list(ALL_ROLE_CODES),
        },
        "ContentDownloadTokenViewSet": {
            "list": list(ALL_ROLE_CODES),
            "create": list(ALL_ROLE_CODES),
        },
    },
    "logistics": {
        "WarehouseViewSet": {
            "list": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "retrieve": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "create": [ADMIN_ROLE_CODE],
            "update": [ADMIN_ROLE_CODE],
            "partial_update": [ADMIN_ROLE_CODE],
            "destroy": [ADMIN_ROLE_CODE],
        },
        "ZoneViewSet": {
            "list": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "retrieve": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "create": [ADMIN_ROLE_CODE],
            "update": [ADMIN_ROLE_CODE],
            "partial_update": [ADMIN_ROLE_CODE],
            "destroy": [ADMIN_ROLE_CODE],
        },
        "LocationViewSet": {
            "list": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "retrieve": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "create": [ADMIN_ROLE_CODE],
            "update": [ADMIN_ROLE_CODE],
            "partial_update": [ADMIN_ROLE_CODE],
            "destroy": [ADMIN_ROLE_CODE],
        },
        "PickupPointViewSet": {
            "list": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE, GROUP_LEADER_ROLE_CODE],
            "retrieve": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                GROUP_LEADER_ROLE_CODE,
            ],
            "create": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "update": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "partial_update": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                GROUP_LEADER_ROLE_CODE,
            ],
            "destroy": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
        },
        "PickupPointBusinessHourViewSet": {
            "list": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE, GROUP_LEADER_ROLE_CODE],
            "retrieve": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                GROUP_LEADER_ROLE_CODE,
            ],
            "create": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "update": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "partial_update": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
            "destroy": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE],
        },
        "PickupPointClosureViewSet": {
            "list": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE, GROUP_LEADER_ROLE_CODE],
            "retrieve": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                GROUP_LEADER_ROLE_CODE,
            ],
            "create": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE, GROUP_LEADER_ROLE_CODE],
            "update": [ADMIN_ROLE_CODE, CLUB_MANAGER_ROLE_CODE, GROUP_LEADER_ROLE_CODE],
            "partial_update": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                GROUP_LEADER_ROLE_CODE,
            ],
            "destroy": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                GROUP_LEADER_ROLE_CODE,
            ],
        },
        "GroupLeaderOnboardingViewSet": {
            "list": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                COUNSELOR_REVIEWER_ROLE_CODE,
                GROUP_LEADER_ROLE_CODE,
            ],
            "retrieve": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                COUNSELOR_REVIEWER_ROLE_CODE,
                GROUP_LEADER_ROLE_CODE,
            ],
            "create": [
                ADMIN_ROLE_CODE,
                CLUB_MANAGER_ROLE_CODE,
                COUNSELOR_REVIEWER_ROLE_CODE,
                GROUP_LEADER_ROLE_CODE,
                MEMBER_ROLE_CODE,
            ],
            "review": [COUNSELOR_REVIEWER_ROLE_CODE],
        },
    },
}
