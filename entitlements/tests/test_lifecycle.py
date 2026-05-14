from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from entitlements.models import Entitlement, Product


class LifecycleMatrixTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("alice")
        self.digital = Product.objects.get(name="Digital")
        self.printp = Product.objects.get(name="Print")
        self.premium = Product.objects.get(name="Premium")

    def _features(self, at=None):
        return Entitlement.objects.features_for(self.user, at=at)

    def test_grant_digital_features_now(self):
        Entitlement.objects.create(user=self.user, product=self.digital)
        self.assertEqual(self._features(), {"web_access"})

    def test_expired_grant_is_inactive(self):
        now = timezone.now()
        Entitlement.objects.create(
            user=self.user,
            product=self.premium,
            expires_at=now + timedelta(days=1),
        )
        self.assertEqual(self._features(at=now + timedelta(days=2)), set())

    def test_revoked_grant_is_inactive_immediately(self):
        e = Entitlement.objects.create(user=self.user, product=self.premium)
        self.assertEqual(self._features(), {"web_access", "print_magazine", "ad_free"})
        e.revoke()
        self.assertEqual(self._features(), set())

    def test_revoke_before_expiry_kills_access_forever(self):
        now = timezone.now()
        e = Entitlement.objects.create(
            user=self.user,
            product=self.premium,
            expires_at=now + timedelta(days=7),
        )
        e.revoke()
        self.assertEqual(self._features(), set())
        self.assertEqual(self._features(at=now + timedelta(days=3)), set())

    def test_revocation_is_absolute_in_time_travel(self):
        """A revoked entitlement is inactive even at timestamps before the revoke."""
        granted = timezone.now() - timedelta(days=10)
        e = Entitlement.objects.create(
            user=self.user, product=self.premium, granted_at=granted
        )
        e.revoke()
        # query at a time *before* the revoke happened
        self.assertEqual(self._features(at=granted + timedelta(days=1)), set())

    def test_overlapping_grants_union_features(self):
        Entitlement.objects.create(user=self.user, product=self.digital)
        Entitlement.objects.create(user=self.user, product=self.premium)
        self.assertEqual(
            self._features(),
            {"web_access", "print_magazine", "ad_free"},
        )

    def test_query_before_granted_at(self):
        now = timezone.now()
        Entitlement.objects.create(
            user=self.user,
            product=self.premium,
            granted_at=now,
        )
        self.assertEqual(self._features(at=now - timedelta(seconds=1)), set())

    def test_revoke_is_idempotent(self):
        e = Entitlement.objects.create(user=self.user, product=self.premium)
        self.assertTrue(e.revoke())
        first = e.revoked_at
        self.assertFalse(e.revoke())
        e.refresh_from_db()
        self.assertEqual(e.revoked_at, first)

    def test_no_entitlements_returns_empty_features(self):
        self.assertEqual(self._features(), set())

    def test_active_for_excludes_expired_and_revoked(self):
        now = timezone.now()
        active = Entitlement.objects.create(user=self.user, product=self.digital)
        expired = Entitlement.objects.create(
            user=self.user,
            product=self.printp,
            granted_at=now - timedelta(days=2),
            expires_at=now - timedelta(days=1),
        )
        revoked = Entitlement.objects.create(user=self.user, product=self.premium)
        revoked.revoke()

        active_ids = set(
            Entitlement.objects.active_for(self.user).values_list("id", flat=True)
        )
        self.assertEqual(active_ids, {active.id})
        self.assertNotIn(expired.id, active_ids)
        self.assertNotIn(revoked.id, active_ids)
