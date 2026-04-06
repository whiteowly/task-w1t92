try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):
        pass


class RoleCode(StrEnum):
    ADMINISTRATOR = "administrator"
    CLUB_MANAGER = "club_manager"
    COUNSELOR_REVIEWER = "counselor_reviewer"
    GROUP_LEADER = "group_leader"
    MEMBER = "member"
