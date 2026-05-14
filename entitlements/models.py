from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Feature(models.Model):
    name = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=64, unique=True)
    features = models.ManyToManyField(Feature, related_name="products")

    def __str__(self):
        return self.name


class EntitlementQuerySet(models.QuerySet):
    def active_for(self, user, at=None):
        at = at or timezone.now()
        return self.filter(
            user=user,
            revoked_at__isnull=True,
            granted_at__lte=at,
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=at))

    def features_for(self, user, at=None):
        active = self.active_for(user, at=at)
        return set(
            Feature.objects.filter(products__entitlement_set__in=active)
            .values_list("name", flat=True)
            .distinct()
        )


class Entitlement(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="entitlements",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="entitlement_set",
    )
    granted_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = EntitlementQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["user", "revoked_at", "expires_at"]),
        ]
        ordering = ["-granted_at"]

    def is_active(self, at=None):
        at = at or timezone.now()
        if self.revoked_at is not None:
            return False
        if self.granted_at > at:
            return False
        if self.expires_at is not None and self.expires_at <= at:
            return False
        return True

    def revoke(self, at=None):
        if self.revoked_at is not None:
            return False
        self.revoked_at = at or timezone.now()
        self.save(update_fields=["revoked_at"])
        return True

    def __str__(self):
        return f"{self.user_id} -> {self.product.name}"
