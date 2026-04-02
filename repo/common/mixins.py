from rest_framework.exceptions import PermissionDenied


class OrganizationScopedViewSetMixin:
    organization_field = "organization"

    def get_organization(self):
        organization = getattr(self.request, "organization", None)
        if organization is None:
            raise PermissionDenied("No active organization in session.")
        return organization

    def get_queryset(self):
        queryset = super().get_queryset()
        organization = self.get_organization()
        return queryset.filter(**{f"{self.organization_field}_id": organization.id})

    def perform_create(self, serializer):
        serializer.save(**{self.organization_field: self.get_organization()})
