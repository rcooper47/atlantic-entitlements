from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from entitlements.models import Entitlement, Feature, Product


class CatalogSeedTests(TestCase):
    def test_three_products_seeded(self):
        names = set(Product.objects.values_list("name", flat=True))
        self.assertEqual(names, {"Digital", "Print", "Premium"})

    def test_product_feature_links(self):
        digital = Product.objects.get(name="Digital")
        printp = Product.objects.get(name="Print")
        premium = Product.objects.get(name="Premium")

        self.assertEqual(
            set(digital.features.values_list("name", flat=True)),
            {"web_access"},
        )
        self.assertEqual(
            set(printp.features.values_list("name", flat=True)),
            {"web_access", "print_magazine"},
        )
        self.assertEqual(
            set(premium.features.values_list("name", flat=True)),
            {"web_access", "print_magazine", "ad_free"},
        )

    def test_features_are_unique_rows(self):
        names = list(Feature.objects.values_list("name", flat=True))
        self.assertEqual(len(names), len(set(names)))
        with self.assertRaises(IntegrityError):
            Feature.objects.create(name="web_access")


class EntitlementDefaultsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("alice")
        self.digital = Product.objects.get(name="Digital")

    def test_granted_at_defaults_to_now(self):
        before = timezone.now()
        e = Entitlement.objects.create(user=self.user, product=self.digital)
        after = timezone.now()
        self.assertGreaterEqual(e.granted_at, before)
        self.assertLessEqual(e.granted_at, after)
        self.assertIsNone(e.expires_at)
        self.assertIsNone(e.revoked_at)
