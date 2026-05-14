import base64
import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse


def basic_auth(username, password):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


class BasicAuthMiddlewareTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            "curl-admin", password="curl-pw", is_staff=True
        )
        self.subject = User.objects.create_user("subject")
        self.client = Client()

    def test_basic_auth_grants_access_to_staff_endpoint(self):
        response = self.client.post(
            reverse("entitlements:user-entitlements", args=[self.subject.id]),
            data=json.dumps({"product_name": "Digital"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=basic_auth("curl-admin", "curl-pw"),
        )
        self.assertEqual(response.status_code, 201)

    def test_basic_auth_with_bad_password_falls_through_to_401(self):
        response = self.client.get(
            reverse("entitlements:user-entitlements", args=[self.subject.id]),
            HTTP_AUTHORIZATION=basic_auth("curl-admin", "wrong-pw"),
        )
        self.assertEqual(response.status_code, 401)

    def test_malformed_header_falls_through_to_401(self):
        response = self.client.get(
            reverse("entitlements:user-entitlements", args=[self.subject.id]),
            HTTP_AUTHORIZATION="Basic !!!not-base64!!!",
        )
        self.assertEqual(response.status_code, 401)

    def test_no_auth_header_returns_401(self):
        response = self.client.get(
            reverse("entitlements:user-entitlements", args=[self.subject.id]),
        )
        self.assertEqual(response.status_code, 401)
