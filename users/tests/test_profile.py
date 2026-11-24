from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken


User = get_user_model()


class UserProfileTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="profile@example.com",
            password="StrongPassword123!",
            first_name="John",
            last_name="Doe",
        )
        self.url = reverse("user-profile")

    def authenticate(self):
        refresh = RefreshToken.for_user(self.user)
        access_token = str(refresh.access_token)

        self.client.credentials(
            HTTP_AUTHORIZE=f"Bearer {access_token}"
        )

    def test_profile_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_get_own_profile(self):
        self.authenticate()

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code, status.HTTP_200_OK
        )
        self.assertEqual(
            response.data["email"], self.user.email
        )
        self.assertEqual(
            response.data["first_name"], "John"
        )
        self.assertNotIn("password", response.data)

    def test_update_profile_patch(self):
        self.authenticate()

        response = self.client.patch(
            self.url,
            {"first_name": "Michael"},
            format="json",
        )

        self.assertEqual(
            response.status_code, status.HTTP_200_OK
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Michael")

    def test_update_profile_put(self):
        self.authenticate()

        response = self.client.put(
            self.url,
            {
                "email": self.user.email,
                "first_name": "Jane",
                "last_name": "Smith",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code, status.HTTP_200_OK
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Jane")
        self.assertEqual(self.user.last_name, "Smith")

    def test_cannot_change_staff_status(self):
        self.authenticate()

        response = self.client.patch(
            self.url,
            {"is_staff": True},
            format="json",
        )

        self.assertEqual(
            response.status_code, status.HTTP_200_OK
        )

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)

    def test_cannot_update_without_authentication(self):
        response = self.client.patch(
            self.url,
            {"first_name": "Hacker"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_cannot_use_existing_email(self):
        User.objects.create_user(
            email="existing@example.com",
            password="StrongPassword123!",
        )
        self.authenticate()

        response = self.client.patch(
            self.url,
            {"email": "existing@example.com"},
            format="json",
        )

        self.assertEqual(
            response.status_code, status.HTTP_400_BAD_REQUEST
        )
