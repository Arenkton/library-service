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


class CreateBorrowingAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
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
            inventory=3,
            daily_fee=Decimal("1.50"),
        )

    def setUp(self):
        self.url = reverse("borrowing-list")
        self.return_date = (
            timezone.localdate() + timedelta(days=7)
        )

        self.valid_data = {
            "book": self.book.pk,
            "expected_return_date": self.return_date.isoformat(),
        }

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(
            HTTP_AUTHORIZE=f"Bearer {token}"
        )

    def post_borrowing(self, data=None):
        if data is None:
            data = self.valid_data

        return self.client.post(
            self.url,
            data,
            format="json",
        )

    def test_user_can_create_borrowing(self):
        self.authenticate(self.user)

        response = self.post_borrowing()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(Borrowing.objects.count(), 1)

        borrowing = Borrowing.objects.get()

        self.assertEqual(borrowing.user, self.user)
        self.assertEqual(borrowing.book, self.book)
        self.assertEqual(
            borrowing.expected_return_date,
            self.return_date,
        )
        self.assertEqual(
            borrowing.borrow_date,
            timezone.localdate(),
        )
        self.assertIsNone(borrowing.actual_return_date)

    def test_inventory_decreases_after_creation(self):
        self.authenticate(self.user)

        response = self.post_borrowing()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 2)

    def test_admin_can_create_borrowing(self):
        self.authenticate(self.admin)

        response = self.post_borrowing()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            Borrowing.objects.get().user,
            self.admin,
        )

    def test_anonymous_user_cannot_create_borrowing(self):
        response = self.post_borrowing()

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(Borrowing.objects.count(), 0)

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 3)

    def test_invalid_jwt_cannot_create_borrowing(self):
        self.client.credentials(
            HTTP_AUTHORIZE="Bearer invalid-token"
        )

        response = self.post_borrowing()

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(Borrowing.objects.count(), 0)

    def test_user_cannot_forge_borrowing_owner(self):
        self.authenticate(self.user)

        data = {
            **self.valid_data,
            "user": self.other_user.pk,
        }

        response = self.post_borrowing(data)

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            Borrowing.objects.get().user,
            self.user,
        )

    def test_actual_return_date_cannot_be_set(self):
        self.authenticate(self.user)

        data = {
            **self.valid_data,
            "actual_return_date": (
                timezone.localdate().isoformat()
            ),
        }

        response = self.post_borrowing(data)

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertIsNone(
            Borrowing.objects.get().actual_return_date
        )

    def test_can_borrow_last_available_copy(self):
        self.book.inventory = 1
        self.book.save(update_fields=["inventory"])

        self.authenticate(self.user)

        response = self.post_borrowing()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 0)

    def test_cannot_borrow_out_of_stock_book(self):
        self.book.inventory = 0
        self.book.save(update_fields=["inventory"])

        self.authenticate(self.user)

        response = self.post_borrowing()

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("book", response.data)
        self.assertEqual(Borrowing.objects.count(), 0)

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 0)

    def test_cannot_borrow_twice_when_one_copy_left(self):
        self.book.inventory = 1
        self.book.save(update_fields=["inventory"])

        self.authenticate(self.user)

        first_response = self.post_borrowing()
        second_response = self.post_borrowing()

        self.assertEqual(
            first_response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            second_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(Borrowing.objects.count(), 1)

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 0)

    def test_missing_book_is_rejected(self):
        self.authenticate(self.user)

        data = {
            "expected_return_date": self.return_date.isoformat(),
        }

        response = self.post_borrowing(data)

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("book", response.data)
        self.assertEqual(Borrowing.objects.count(), 0)

    def test_nonexistent_book_is_rejected(self):
        self.authenticate(self.user)

        data = {
            **self.valid_data,
            "book": 999999,
        }

        response = self.post_borrowing(data)

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("book", response.data)
        self.assertEqual(Borrowing.objects.count(), 0)

    def test_missing_return_date_is_rejected(self):
        self.authenticate(self.user)

        response = self.post_borrowing(
            {"book": self.book.pk}
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn(
            "expected_return_date",
            response.data,
        )
        self.assertEqual(Borrowing.objects.count(), 0)

    def test_today_return_date_is_rejected(self):
        self.authenticate(self.user)

        data = {
            **self.valid_data,
            "expected_return_date": (
                timezone.localdate().isoformat()
            ),
        }

        response = self.post_borrowing(data)

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(Borrowing.objects.count(), 0)

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 3)

    def test_past_return_date_is_rejected(self):
        self.authenticate(self.user)

        yesterday = (
            timezone.localdate() - timedelta(days=1)
        )

        data = {
            **self.valid_data,
            "expected_return_date": yesterday.isoformat(),
        }

        response = self.post_borrowing(data)

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(Borrowing.objects.count(), 0)

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 3)

    def test_invalid_date_format_is_rejected(self):
        self.authenticate(self.user)

        data = {
            **self.valid_data,
            "expected_return_date": "not-a-date",
        }

        response = self.post_borrowing(data)

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn(
            "expected_return_date",
            response.data,
        )

    def test_other_book_inventory_does_not_change(self):
        other_book = Book.objects.create(
            title="Dune",
            author="Frank Herbert",
            cover="SOFT",
            inventory=7,
            daily_fee=Decimal("2.50"),
        )

        self.authenticate(self.user)

        response = self.post_borrowing()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        other_book.refresh_from_db()
        self.book.refresh_from_db()

        self.assertEqual(other_book.inventory, 7)
        self.assertEqual(self.book.inventory, 2)

    def test_inventory_rolls_back_on_creation_error(self):
        self.authenticate(self.user)

        with patch.object(
            Borrowing.objects,
            "create",
            side_effect=RuntimeError("Database write failed"),
        ):
            with self.assertRaises(RuntimeError):
                self.post_borrowing()

        self.book.refresh_from_db()

        self.assertEqual(self.book.inventory, 3)
        self.assertEqual(Borrowing.objects.count(), 0)
