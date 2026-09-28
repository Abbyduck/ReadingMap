from urllib.parse import urlparse, parse_qs
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient
from .models import User

class AuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        self.password = "Wisteria!River@42"

    def token(self, client=None):
        return (client or self.client).get("/api/auth/csrf").json()["csrfToken"]

    def post(self, path, data=None, client=None):
        client = client or self.client
        return client.post("/api/auth/" + path, data or {}, format="json", HTTP_X_CSRFTOKEN=self.token(client))

    def test_guest_me_and_csrf_required_even_before_login(self):
        self.assertEqual(self.client.get("/api/auth/me").json(), {"user": None})
        for endpoint in ["register", "login", "logout", "password-reset", "password-reset/confirm"]:
            self.assertEqual(self.client.post("/api/auth/" + endpoint, {}, format="json").status_code, 403)

    def test_register_login_logout_email_normalization_and_no_staff_escalation(self):
        result = self.post("register", {"email": "Parent@Example.COM", "password": self.password, "name": "家长", "is_staff": True, "is_superuser": True})
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.json()["user"]["email"], "parent@example.com")
        self.assertFalse(result.json()["user"]["is_staff"])
        self.assertFalse(User.objects.get().is_superuser)
        self.assertTrue(User.objects.get().check_password(self.password))
        self.assertEqual(self.post("logout").status_code, 204)
        self.assertIsNone(self.client.get("/api/auth/me").json()["user"])
        self.assertEqual(self.post("login", {"email": "PARENT@example.com", "password": self.password}).status_code, 200)
        self.assertEqual(self.post("register", {"email": "parent@example.com", "password": self.password}).status_code, 400)

    def test_password_rules_bad_login_and_inactive_account(self):
        self.assertEqual(self.post("register", {"email": "parent@example.com", "password": "0" * 6}).status_code, 400)
        self.assertEqual(User.objects.count(), 0)
        User.objects.create_user("parent@example.com", self.password, is_active=False)
        self.assertEqual(self.post("login", {"email": "parent@example.com", "password": self.password}).status_code, 400)
        self.assertEqual(self.post("login", {"email": "missing@example.com", "password": self.password}).status_code, 400)

    def test_reset_generic_response_single_use_token_and_invalidated_sessions(self):
        user = User.objects.create_user("parent@example.com", self.password)
        self.post("login", {"email": user.email, "password": self.password})
        previous_session_client = APIClient()
        previous_session_client.cookies = self.client.cookies.copy()
        known = self.post("password-reset", {"email": user.email})
        unknown = self.post("password-reset", {"email": "missing@example.com"})
        self.assertEqual(known.json(), unknown.json())
        self.assertEqual(len(mail.outbox), 1)
        link = next(line for line in mail.outbox[0].body.splitlines() if line.startswith("http"))
        query = parse_qs(urlparse(link).query)
        payload = {"uid": query["uid"][0], "token": query["token"][0], "password": "Meadow!Another@73"}
        self.assertEqual(self.post("password-reset/confirm", payload).status_code, 200)
        self.assertIsNone(previous_session_client.get("/api/auth/me").json()["user"])
        self.assertEqual(self.post("password-reset/confirm", payload).status_code, 400)
        user.refresh_from_db()
        self.assertTrue(user.check_password(payload["password"]))

    def test_invalid_reset_ids_and_token_expiry(self):
        self.assertEqual(self.post("password-reset/confirm", {"uid": "!!!!!", "token": "no", "password": self.password}).status_code, 400)
        user = User.objects.create_user("parent@example.com", self.password)
        token = default_token_generator.make_token(user)
        with override_settings(PASSWORD_RESET_TIMEOUT=-1):
            result = self.post("password-reset/confirm", {"uid": urlsafe_base64_encode(force_bytes(user.pk)), "token": token, "password": self.password})
        self.assertEqual(result.status_code, 400)

    def test_auth_rate_limit(self):
        for _ in range(20):
            self.post("login", {"email": "missing@example.com", "password": self.password})
        self.assertEqual(self.post("login", {"email": "missing@example.com", "password": self.password}).status_code, 429)
