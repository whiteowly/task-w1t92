from django.db import models


class OrganizationScopedQuerySet(models.QuerySet):
    def for_organization(self, organization):
        org_id = getattr(organization, "id", organization)
        return self.filter(organization_id=org_id)


class OrganizationScopedManager(models.Manager):
    def get_queryset(self):
        return OrganizationScopedQuerySet(self.model, using=self._db)

    def for_organization(self, organization):
        return self.get_queryset().for_organization(organization)
