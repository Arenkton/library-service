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


class BorrowingAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()

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
            title="The Hobbit",
            author="J. R. R. Tolkien",
            cover="HARD",
            inventory=5,
            daily_fee=Decimal("1.50"),
        )

        cls.own_borrowing = Borrowing.objects.create(
            user=cls.user,
            book=cls.book,
            expected_return_date=today + timedelta(days=14),
        )
        cls.other_borrowing = Borrowing.objects.create(
            user=cls.other_user,
            book=cls.book,
            expected_return_date=today + timedelta(days=7),
        )
        cls.returned_borrowing = Borrowing.objects.create(
            user=cls.user,
            book=cls.book,
            expected_return_date=today + timedelta(days=10),
            actual_return_date=today,
        )

    def setUp(self):
        self.list_url = reverse("borrowing-list")
        self.detail_url = reverse(
            "borrowing-detail",
            args=[self.own_borrowing.pk],
        )

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(
            HTTP_AUTHORIZE=f"Bearer {token}"
        )

    def test_anonymous_cannot_list_borrowings(self):
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_anonymous_cannot_retrieve_borrowing(self):
        response = self.client.get(self.detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_invalid_jwt_is_rejected(self):
        self.client.credentials(
            HTTP_AUTHORIZE="Bearer invalid-token"
        )

        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_user_sees_only_own_borrowings(self):
        self.authenticate(self.user)

        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = {
            item["id"] for item in response.data
        }
        expected_ids = {
            self.own_borrowing.id,
            self.returned_borrowing.id,
        }

        self.assertEqual(returned_ids, expected_ids)

    def test_other_user_sees_only_their_borrowings(self):
        self.authenticate(self.other_user)

        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            [item["id"] for item in response.data],
            [self.other_borrowing.id],
        )

    def test_user_can_retrieve_own_borrowing(self):
        self.authenticate(self.user)

        response = self.client.get(self.detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["id"],
            self.own_borrowing.id,
        )

    def test_user_cannot_retrieve_other_borrowing(self):
        self.authenticate(self.user)

        url = reverse(
            "borrowing-detail",
            args=[self.other_borrowing.id],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_user_id_parameter_cannot_bypass_permissions(self):
        self.authenticate(self.user)

        response = self.client.get(
            self.list_url,
            {"user_id": self.other_user.id},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = {
            item["id"] for item in response.data
        }
        self.assertNotIn(
            self.other_borrowing.id,
            returned_ids,
        )

    def test_admin_can_list_all_borrowings(self):
        self.authenticate(self.admin)

        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(response.data), 3)

    def test_admin_can_retrieve_other_user_borrowing(self):
        self.authenticate(self.admin)

        url = reverse(
            "borrowing-detail",
            args=[self.other_borrowing.id],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["user"],
            self.other_user.id,
        )

    def test_nonexistent_borrowing_returns_404(self):
        self.authenticate(self.admin)

        url = reverse(
            "borrowing-detail",
            args=[999999],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_detail_contains_nested_book_information(self):
        self.authenticate(self.user)

        response = self.client.get(self.detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["book"]["title"],
            "The Hobbit",
        )
        self.assertEqual(
            response.data["book"]["author"],
            "J. R. R. Tolkien",
        )
        self.assertEqual(
            response.data["book"]["inventory"],
            5,
        )

    def test_active_borrowing_status(self):
        self.authenticate(self.user)

        response = self.client.get(self.detail_url)

        self.assertTrue(response.data["is_active"])
        self.assertIsNone(
            response.data["actual_return_date"]
        )

    def test_returned_borrowing_status(self):
        self.authenticate(self.user)

        url = reverse(
            "borrowing-detail",
            args=[self.returned_borrowing.id],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertFalse(response.data["is_active"])
        self.assertIsNotNone(
            response.data["actual_return_date"]
        )

    def test_post_is_not_allowed_yet(self):
        self.authenticate(self.user)

        response = self.client.post(
            self.list_url,
            {
                "book": self.book.id,
                "expected_return_date": (
                    timezone.localdate()
                    + timedelta(days=7)
                ).isoformat(),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_put_is_not_allowed(self):
        self.authenticate(self.admin)

        response = self.client.put(
            self.detail_url,
            {"expected_return_date": "2027-01-01"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_patch_is_not_allowed(self):
        self.authenticate(self.admin)

        response = self.client.patch(
            self.detail_url,
            {"actual_return_date": "2027-01-01"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_delete_is_not_allowed(self):
        self.authenticate(self.admin)

        response = self.client.delete(self.detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertTrue(
            Borrowing.objects.filter(
                pk=self.own_borrowing.pk
            ).exists()
        )

    def test_get_does_not_change_book_inventory(self):
        self.authenticate(self.user)

        self.client.get(self.list_url)
        self.client.get(self.detail_url)

        self.book.refresh_from_db()

        self.assertEqual(self.book.inventory, 5)
