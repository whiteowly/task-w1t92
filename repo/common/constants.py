from enum import StrEnum


class RoleCode(StrEnum):
    ADMINISTRATOR = "administrator"
    CLUB_MANAGER = "club_manager"
    COUNSELOR_REVIEWER = "counselor_reviewer"
    GROUP_LEADER = "group_leader"
    MEMBER = "member"
