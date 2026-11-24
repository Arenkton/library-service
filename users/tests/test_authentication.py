from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken


User = get_user_model()


class UserAuthenticationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="StrongPassword123!",
        )
        self.token_url = reverse("token-obtain")
        self.refresh_url = reverse("token-refresh")

    def test_get_jwt_tokens(self):
        response = self.client.post(
            self.token_url,
            {
                "email": "test@example.com",
                "password": "StrongPassword123!",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code, status.HTTP_200_OK
        )
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_invalid_password(self):
        response = self.client.post(
            self.token_url,
            {
                "email": "test@example.com",
                "password": "WrongPassword",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_refresh_token(self):
        refresh = RefreshToken.for_user(self.user)

        response = self.client.post(
            self.refresh_url,
            {"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(
            response.status_code, status.HTTP_200_OK
        )
        self.assertIn("access", response.data)

    def test_invalid_refresh_token(self):
        response = self.client.post(
            self.refresh_url,
            {"refresh": "invalid-token"},
            format="json",
        )

        self.assertEqual(
            response.status_code, status.HTTP_401_UNAUTHORIZED
        )
