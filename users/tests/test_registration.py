from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken


User = get_user_model()


class UserRegistrationTests(APITestCase):
    def setUp(self):
        self.url = reverse("user-register")
        self.data = {
            "email": "newuser@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "password": "StrongPassword123!",
        }

    def test_register_user(self):
        response = self.client.post(
            self.url, self.data, format="json"
        )

        self.assertEqual(
            response.status_code, status.HTTP_201_CREATED
        )
        self.assertEqual(User.objects.count(), 1)

        user = User.objects.get(email=self.data["email"])
        self.assertTrue(
            user.check_password(self.data["password"])
        )
        self.assertFalse(user.is_staff)

    def test_password_not_returned(self):
        response = self.client.post(
            self.url, self.data, format="json"
        )

        self.assertEqual(
            response.status_code, status.HTTP_201_CREATED
        )
        self.assertNotIn("password", response.data)

    def test_duplicate_email(self):
        User.objects.create_user(
            email=self.data["email"],
            password="AnotherPassword123!",
        )

        response = self.client.post(
            self.url, self.data, format="json"
        )

        self.assertEqual(
            response.status_code, status.HTTP_400_BAD_REQUEST
        )
        self.assertEqual(User.objects.count(), 1)

    def test_weak_password(self):
        self.data["password"] = "123"

        response = self.client.post(
            self.url, self.data, format="json"
        )

        self.assertEqual(
            response.status_code, status.HTTP_400_BAD_REQUEST
        )

    def test_password_required(self):
        self.data.pop("password")

        response = self.client.post(
            self.url, self.data, format="json"
        )

        self.assertEqual(
            response.status_code, status.HTTP_400_BAD_REQUEST
        )

    def test_registration_cannot_create_staff(self):
        self.data["is_staff"] = True
        self.data["is_superuser"] = True

        response = self.client.post(
            self.url, self.data, format="json"
        )

        self.assertEqual(
            response.status_code, status.HTTP_201_CREATED
        )

        user = User.objects.get(email=self.data["email"])
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
