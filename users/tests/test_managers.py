from django.contrib.auth import get_user_model

from rest_framework.test import APITestCase


User = get_user_model()


class UserManagerTests(APITestCase):
    def test_create_superuser(self):
        admin = User.objects.create_superuser(
            email="admin@example.com",
            password="AdminPassword123!",
        )

        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(
            admin.check_password("AdminPassword123!")
        )

    def test_superuser_requires_staff(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="admin@example.com",
                password="AdminPassword123!",
                is_staff=False,
            )

    def test_superuser_requires_superuser_flag(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="admin@example.com",
                password="AdminPassword123!",
                is_superuser=False,
            )
