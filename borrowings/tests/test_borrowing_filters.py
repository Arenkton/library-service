from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from books.models import Book
from borrowings.models import Borrowing


User = get_user_model()


class BorrowingFilteringTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        return_date = today + timedelta(days=14)

        cls.user = User.objects.create_user(
            email="reader@example.com",
            password="ReaderPassword123!",
        )
        cls.other_user = User.objects.create_user(
            email="other@example.com",
            password="OtherPassword123!",
        )
        cls.admin = User.objects.create_superuser(
            email="admin@example.com",
            password="AdminPassword123!",
        )

        cls.book = Book.objects.create(
            title="Dune",
            author="Frank Herbert",
            cover="HARD",
            inventory=10,
            daily_fee=Decimal("2.50"),
        )

        cls.user_active = Borrowing.objects.create(
            user=cls.user,
            book=cls.book,
            expected_return_date=return_date,
        )
        cls.user_returned = Borrowing.objects.create(
            user=cls.user,
            book=cls.book,
            expected_return_date=return_date,
            actual_return_date=today,
        )
        cls.other_active = Borrowing.objects.create(
            user=cls.other_user,
            book=cls.book,
            expected_return_date=return_date,
        )
        cls.other_returned = Borrowing.objects.create(
            user=cls.other_user,
            book=cls.book,
            expected_return_date=return_date,
            actual_return_date=today,
        )

    def setUp(self):
        self.url = reverse("borrowing-list")

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(
            HTTP_AUTHORIZE=f"Bearer {token}"
        )

    def assert_borrowing_ids(self, response, expected_ids):
        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        actual_ids = {
            item["id"] for item in response.data
        }
        self.assertEqual(actual_ids, set(expected_ids))

    def test_user_sees_only_own_borrowings(self):
        self.authenticate(self.user)

        response = self.client.get(self.url)

        self.assert_borrowing_ids(
            response,
            [self.user_active.id, self.user_returned.id],
        )

    def test_user_filters_active_borrowings(self):
        self.authenticate(self.user)

        response = self.client.get(
            self.url,
            {"is_active": "true"},
        )

        self.assert_borrowing_ids(
            response,
            [self.user_active.id],
        )

    def test_user_filters_returned_borrowings(self):
        self.authenticate(self.user)

        response = self.client.get(
            self.url,
            {"is_active": "false"},
        )

        self.assert_borrowing_ids(
            response,
            [self.user_returned.id],
        )

    def test_user_id_cannot_bypass_permissions(self):
        self.authenticate(self.user)

        response = self.client.get(
            self.url,
            {"user_id": self.other_user.id},
        )

        self.assert_borrowing_ids(
            response,
            [self.user_active.id, self.user_returned.id],
        )

    def test_user_combined_filters_cannot_bypass_permissions(self):
        self.authenticate(self.user)

        response = self.client.get(
            self.url,
            {
                "user_id": self.other_user.id,
                "is_active": "true",
            },
        )

        self.assert_borrowing_ids(
            response,
            [self.user_active.id],
        )

    def test_admin_sees_all_borrowings(self):
        self.authenticate(self.admin)

        response = self.client.get(self.url)

        self.assert_borrowing_ids(
            response,
            [
                self.user_active.id,
                self.user_returned.id,
                self.other_active.id,
                self.other_returned.id,
            ],
        )

    def test_admin_filters_active_borrowings(self):
        self.authenticate(self.admin)

        response = self.client.get(
            self.url,
            {"is_active": "true"},
        )

        self.assert_borrowing_ids(
            response,
            [self.user_active.id, self.other_active.id],
        )

    def test_admin_filters_returned_borrowings(self):
        self.authenticate(self.admin)

        response = self.client.get(
            self.url,
            {"is_active": "false"},
        )

        self.assert_borrowing_ids(
            response,
            [self.user_returned.id, self.other_returned.id],
        )

    def test_admin_filters_by_user_id(self):
        self.authenticate(self.admin)

        response = self.client.get(
            self.url,
            {"user_id": self.user.id},
        )

        self.assert_borrowing_ids(
            response,
            [self.user_active.id, self.user_returned.id],
        )

    def test_admin_filters_by_other_user_id(self):
        self.authenticate(self.admin)

        response = self.client.get(
            self.url,
            {"user_id": self.other_user.id},
        )

        self.assert_borrowing_ids(
            response,
            [self.other_active.id, self.other_returned.id],
        )

    def test_admin_combines_user_and_active_filters(self):
        self.authenticate(self.admin)

        response = self.client.get(
            self.url,
            {
                "user_id": self.other_user.id,
                "is_active": "true",
            },
        )

        self.assert_borrowing_ids(
            response,
            [self.other_active.id],
        )

    def test_admin_combines_user_and_returned_filters(self):
        self.authenticate(self.admin)

        response = self.client.get(
            self.url,
            {
                "user_id": self.user.id,
                "is_active": "false",
            },
        )

        self.assert_borrowing_ids(
            response,
            [self.user_returned.id],
        )

    def test_admin_filter_nonexistent_user(self):
        self.authenticate(self.admin)

        response = self.client.get(
            self.url,
            {"user_id": 999999},
        )

        self.assert_borrowing_ids(response, [])

    def test_anonymous_user_cannot_filter(self):
        response = self.client.get(
            self.url,
            {"is_active": "true"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_invalid_is_active_value(self):
        self.authenticate(self.user)

        response = self.client.get(
            self.url,
            {"is_active": "maybe"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("is_active", response.data)

    def test_invalid_user_id_value(self):
        self.authenticate(self.admin)

        response = self.client.get(
            self.url,
            {"user_id": "abc"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("user_id", response.data)

    def test_user_id_cannot_be_zero(self):
        self.authenticate(self.admin)

        response = self.client.get(
            self.url,
            {"user_id": 0},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("user_id", response.data)
