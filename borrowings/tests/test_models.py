from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from books.models import Book
from borrowings.models import Borrowing


User = get_user_model()


class BorrowingModelTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()

        self.user = User.objects.create_user(
            email="reader@example.com",
            password="TestPassword123!",
        )

        self.book = Book.objects.create(
            title="The Hobbit",
            author="J. R. R. Tolkien",
            cover="HARD",
            inventory=5,
            daily_fee=Decimal("1.50"),
        )

        self.borrowing = Borrowing.objects.create(
            user=self.user,
            book=self.book,
            expected_return_date=self.today + timedelta(days=14),
        )

    def test_borrowing_created_successfully(self):
        self.assertEqual(self.borrowing.user, self.user)
        self.assertEqual(self.borrowing.book, self.book)
        self.assertEqual(self.borrowing.borrow_date, self.today)

    def test_actual_return_date_is_null_by_default(self):
        self.assertIsNone(
            self.borrowing.actual_return_date
        )

    def test_new_borrowing_is_active(self):
        self.assertTrue(self.borrowing.is_active)

    def test_returned_borrowing_is_not_active(self):
        self.borrowing.actual_return_date = self.today
        self.borrowing.save()

        self.assertFalse(self.borrowing.is_active)

    def test_expected_return_date_cannot_equal_borrow_date(self):
        self.borrowing.expected_return_date = (
            self.borrowing.borrow_date
        )

        with self.assertRaises(ValidationError):
            self.borrowing.full_clean()

    def test_expected_return_date_cannot_be_before_borrow_date(self):
        self.borrowing.expected_return_date = (
            self.borrowing.borrow_date - timedelta(days=1)
        )

        with self.assertRaises(ValidationError):
            self.borrowing.full_clean()

    def test_expected_return_date_after_borrow_date_is_valid(self):
        self.borrowing.expected_return_date = (
            self.borrowing.borrow_date + timedelta(days=1)
        )

        self.borrowing.full_clean()

    def test_actual_return_date_cannot_be_before_borrow_date(self):
        self.borrowing.actual_return_date = (
            self.borrowing.borrow_date - timedelta(days=1)
        )

        with self.assertRaises(ValidationError):
            self.borrowing.full_clean()

    def test_actual_return_date_can_equal_borrow_date(self):
        self.borrowing.actual_return_date = (
            self.borrowing.borrow_date
        )

        self.borrowing.full_clean()

    def test_actual_return_date_can_be_after_expected_date(self):
        self.borrowing.actual_return_date = (
            self.borrowing.expected_return_date
            + timedelta(days=3)
        )

        self.borrowing.full_clean()

    def test_book_reverse_relationship(self):
        self.assertIn(
            self.borrowing,
            self.book.borrowings.all(),
        )

    def test_user_reverse_relationship(self):
        self.assertIn(
            self.borrowing,
            self.user.borrowings.all(),
        )

    def test_string_representation(self):
        self.assertEqual(
            str(self.borrowing),
            f"Borrowing #{self.borrowing.pk}: The Hobbit",
        )
