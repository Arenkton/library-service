from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from books.models import Book
from borrowings.models import Borrowing


User = get_user_model()


class ReturnBorrowingAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        expected_return = today + timedelta(days=14)

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
            inventory=2,
            daily_fee=Decimal("1.50"),
        )
        cls.other_book = Book.objects.create(
            title="Dune",
            author="Frank Herbert",
            cover="SOFT",
            inventory=4,
            daily_fee=Decimal("2.50"),
        )

        cls.borrowing = Borrowing.objects.create(
            user=cls.user,
            book=cls.book,
            expected_return_date=expected_return,
        )
        cls.other_borrowing = Borrowing.objects.create(
            user=cls.other_user,
            book=cls.book,
            expected_return_date=expected_return,
        )
        cls.returned_borrowing = Borrowing.objects.create(
            user=cls.user,
            book=cls.book,
            expected_return_date=expected_return,
            actual_return_date=today,
        )

    def setUp(self):
        self.return_url = reverse(
            "borrowing-return-book",
            args=[self.borrowing.pk],
        )

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(
            HTTP_AUTHORIZE=f"Bearer {token}"
        )

    def test_user_can_return_own_borrowing(self):
        self.authenticate(self.user)

        response = self.client.post(self.return_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.borrowing.refresh_from_db()
        self.assertIsNotNone(
            self.borrowing.actual_return_date
        )
        self.assertFalse(self.borrowing.is_active)

    def test_return_date_is_set_to_today(self):
        self.authenticate(self.user)

        self.client.post(self.return_url)

        self.borrowing.refresh_from_db()

        self.assertEqual(
            self.borrowing.actual_return_date,
            timezone.localdate(),
        )

    def test_book_inventory_increases_by_one(self):
        self.authenticate(self.user)

        response = self.client.post(self.return_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 3)

    def test_response_contains_updated_borrowing(self):
        self.authenticate(self.user)

        response = self.client.post(self.return_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["id"],
            self.borrowing.id,
        )
        self.assertFalse(response.data["is_active"])
        self.assertEqual(
            response.data["actual_return_date"],
            timezone.localdate().isoformat(),
        )
        self.assertEqual(
            response.data["book"]["inventory"],
            3,
        )

    def test_cannot_return_borrowing_twice(self):
        self.authenticate(self.user)

        first_response = self.client.post(self.return_url)
        second_response = self.client.post(self.return_url)

        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            second_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 3)

    def test_already_returned_borrowing_is_rejected(self):
        self.authenticate(self.user)

        url = reverse(
            "borrowing-return-book",
            args=[self.returned_borrowing.pk],
        )

        response = self.client.post(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 2)

    def test_return_does_not_change_other_borrowing(self):
        self.authenticate(self.user)

        self.client.post(self.return_url)

        self.other_borrowing.refresh_from_db()

        self.assertIsNone(
            self.other_borrowing.actual_return_date
        )
        self.assertTrue(self.other_borrowing.is_active)

    def test_return_does_not_change_other_book_inventory(self):
        self.authenticate(self.user)

        self.client.post(self.return_url)

        self.other_book.refresh_from_db()

        self.assertEqual(
            self.other_book.inventory,
            4,
        )

    def test_admin_can_return_another_users_borrowing(self):
        self.authenticate(self.admin)

        url = reverse(
            "borrowing-return-book",
            args=[self.other_borrowing.pk],
        )

        response = self.client.post(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.other_borrowing.refresh_from_db()
        self.assertFalse(self.other_borrowing.is_active)

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 3)

    def test_user_cannot_return_another_users_borrowing(self):
        self.authenticate(self.user)

        url = reverse(
            "borrowing-return-book",
            args=[self.other_borrowing.pk],
        )

        response = self.client.post(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.other_borrowing.refresh_from_db()
        self.assertTrue(self.other_borrowing.is_active)

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 2)

    def test_anonymous_user_cannot_return_borrowing(self):
        response = self.client.post(self.return_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        self.borrowing.refresh_from_db()
        self.assertTrue(self.borrowing.is_active)

    def test_invalid_jwt_is_rejected(self):
        self.client.credentials(
            HTTP_AUTHORIZE="Bearer invalid-token"
        )

        response = self.client.post(self.return_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 2)

    def test_nonexistent_borrowing_returns_404(self):
        self.authenticate(self.admin)

        url = reverse(
            "borrowing-return-book",
            args=[999999],
        )

        response = self.client.post(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_get_return_endpoint_is_not_allowed(self):
        self.authenticate(self.user)

        response = self.client.get(self.return_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_put_return_endpoint_is_not_allowed(self):
        self.authenticate(self.user)

        response = self.client.put(
            self.return_url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_patch_return_endpoint_is_not_allowed(self):
        self.authenticate(self.user)

        response = self.client.patch(
            self.return_url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_user_cannot_set_custom_return_date(self):
        self.authenticate(self.user)

        future_date = (
            timezone.localdate() + timedelta(days=30)
        )

        response = self.client.post(
            self.return_url,
            {"actual_return_date": future_date.isoformat()},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.borrowing.refresh_from_db()

        self.assertEqual(
            self.borrowing.actual_return_date,
            timezone.localdate(),
        )

    def test_transaction_rolls_back_if_inventory_update_fails(self):
        self.authenticate(self.user)

        with patch(
            "borrowings.views.Book.objects.filter",
            side_effect=RuntimeError("Inventory update failed"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(self.return_url)

        self.borrowing.refresh_from_db()
        self.book.refresh_from_db()

        self.assertIsNone(
            self.borrowing.actual_return_date
        )
        self.assertTrue(self.borrowing.is_active)
        self.assertEqual(self.book.inventory, 2)
