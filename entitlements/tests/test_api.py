import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from entitlements.models import Entitlement


class ApiTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user("admin", is_staff=True)
        self.reader = User.objects.create_user("reader")
        self.subject = User.objects.create_user("subject")

        self.staff_client = Client()
        self.staff_client.force_login(self.staff)

        self.reader_client = Client()
        self.reader_client.force_login(self.reader)

        self.anon_client = Client()

    def _grant(self, product_name, expires_at=None):
        body = {"product_name": product_name}
        if expires_at is not None:
            body["expires_at"] = expires_at
        return self.staff_client.post(
            reverse("entitlements:user-entitlements", args=[self.subject.id]),
            data=json.dumps(body),
            content_type="application/json",
        )

    def _list_active(self, client=None):
        client = client or self.reader_client
        return client.get(
            reverse("entitlements:user-entitlements", args=[self.subject.id]),
            {"active": "true"},
        )

    def _list_all(self, client=None):
        client = client or self.reader_client
        return client.get(
            reverse("entitlements:user-entitlements", args=[self.subject.id])
        )


class GrantTests(ApiTestCase):
    def test_grant_creates_entitlement(self):
        response = self._grant("Digital")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["product_name"], "Digital")
        self.assertEqual(body["user_id"], self.subject.id)
        self.assertIsNone(body["expires_at"])
        self.assertIsNone(body["revoked_at"])
        self.assertEqual(Entitlement.objects.filter(user=self.subject).count(), 1)

    def test_grant_with_expires_at(self):
        in_future = (timezone.now() + timedelta(days=30)).isoformat()
        response = self._grant("Premium", expires_at=in_future)
        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(response.json()["expires_at"])

    def test_grant_missing_product_name(self):
        response = self.staff_client.post(
            reverse("entitlements:user-entitlements", args=[self.subject.id]),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_grant_unknown_product(self):
        response = self._grant("Platinum")
        self.assertEqual(response.status_code, 404)

    def test_grant_invalid_expires_at(self):
        response = self._grant("Digital", expires_at="not-a-date")
        self.assertEqual(response.status_code, 400)

    def test_grant_unknown_user(self):
        response = self.staff_client.post(
            reverse("entitlements:user-entitlements", args=[999_999]),
            data=json.dumps({"product_name": "Digital"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_grant_requires_staff(self):
        response = self.reader_client.post(
            reverse("entitlements:user-entitlements", args=[self.subject.id]),
            data=json.dumps({"product_name": "Digital"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_grant_anonymous_forbidden(self):
        response = self.anon_client.post(
            reverse("entitlements:user-entitlements", args=[self.subject.id]),
            data=json.dumps({"product_name": "Digital"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)


class ListTests(ApiTestCase):
    def test_active_filter_returns_features(self):
        self._grant("Digital")
        response = self._list_active()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["entitlements"]), 1)
        self.assertEqual(body["features"], ["web_access"])

    def test_full_history_has_no_features_field(self):
        self._grant("Digital")
        response = self._list_all()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("entitlements", body)
        self.assertNotIn("features", body)

    def test_active_filter_excludes_revoked(self):
        grant = self._grant("Premium").json()
        # revoke
        self.staff_client.delete(
            reverse("entitlements:entitlement-detail", args=[grant["id"]])
        )
        response = self._list_active()
        body = response.json()
        self.assertEqual(body["entitlements"], [])
        self.assertEqual(body["features"], [])

    def test_full_history_includes_revoked(self):
        grant = self._grant("Premium").json()
        self.staff_client.delete(
            reverse("entitlements:entitlement-detail", args=[grant["id"]])
        )
        response = self._list_all()
        body = response.json()
        self.assertEqual(len(body["entitlements"]), 1)
        self.assertIsNotNone(body["entitlements"][0]["revoked_at"])

    def test_overlapping_grants_yield_union_features(self):
        self._grant("Digital")
        self._grant("Premium")
        body = self._list_active().json()
        self.assertEqual(
            set(body["features"]),
            {"web_access", "print_magazine", "ad_free"},
        )

    def test_unknown_user_returns_404(self):
        response = self.reader_client.get(
            reverse("entitlements:user-entitlements", args=[999_999])
        )
        self.assertEqual(response.status_code, 404)

    def test_read_requires_authentication(self):
        response = self.anon_client.get(
            reverse("entitlements:user-entitlements", args=[self.subject.id])
        )
        self.assertEqual(response.status_code, 401)


class DeleteTests(ApiTestCase):
    def test_delete_revokes(self):
        grant = self._grant("Premium").json()
        response = self.staff_client.delete(
            reverse("entitlements:entitlement-detail", args=[grant["id"]])
        )
        self.assertEqual(response.status_code, 204)
        Entitlement.objects.get(pk=grant["id"]).revoked_at  # exists
        e = Entitlement.objects.get(pk=grant["id"])
        self.assertIsNotNone(e.revoked_at)

    def test_delete_is_idempotent(self):
        grant = self._grant("Premium").json()
        url = reverse("entitlements:entitlement-detail", args=[grant["id"]])
        self.staff_client.delete(url)
        e = Entitlement.objects.get(pk=grant["id"])
        first_revoked = e.revoked_at

        second = self.staff_client.delete(url)
        self.assertEqual(second.status_code, 204)
        e.refresh_from_db()
        self.assertEqual(e.revoked_at, first_revoked)

    def test_delete_unknown_id(self):
        response = self.staff_client.delete(
            reverse("entitlements:entitlement-detail", args=[999_999])
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_requires_staff(self):
        grant = self._grant("Premium").json()
        response = self.reader_client.delete(
            reverse("entitlements:entitlement-detail", args=[grant["id"]])
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_anonymous_forbidden(self):
        grant = self._grant("Premium").json()
        response = self.anon_client.delete(
            reverse("entitlements:entitlement-detail", args=[grant["id"]])
        )
        self.assertEqual(response.status_code, 401)
