from common.permissions import HasOrganizationRole, IsOrganizationMember


class IsAuthenticatedOrganizationMember(IsOrganizationMember):
    pass


class HasAnyRequiredOrganizationRole(HasOrganizationRole):
    pass
