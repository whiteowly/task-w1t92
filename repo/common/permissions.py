from rest_framework.permissions import BasePermission


class IsOrganizationMember(BasePermission):
    message = "Authentication requires an active organization context."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request, "organization", None)
        )


class HasOrganizationRole(BasePermission):
    message = "Insufficient role for this action."

    def has_permission(self, request, view):
        required_roles = getattr(view, "required_roles", None)
        if not required_roles:
            return True

        role_codes = set(getattr(request, "role_codes", []))
        return any(role in role_codes for role in required_roles)
