from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from books.models import Book
from borrowings.models import Borrowing
from notifications.services import get_overdue_borrowings


User = get_user_model()


class OverdueBorrowingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="reader@example.com",
            password="TestPassword123!",
        )

        cls.book = Book.objects.create(
            title="The Hobbit",
            author="J. R. R. Tolkien",
            cover="HARD",
            inventory=5,
            daily_fee=Decimal("1.50"),
        )

    def test_returns_only_unreturned_borrowings_due_today_or_earlier(
        self,
    ):
        today = timezone.localdate()
        borrow_date = today - timedelta(days=10)

        overdue = Borrowing.objects.create(
            user=self.user,
            book=self.book,
            borrow_date=borrow_date,
            expected_return_date=today - timedelta(days=2),
        )

        due_today = Borrowing.objects.create(
            user=self.user,
            book=self.book,
            borrow_date=borrow_date,
            expected_return_date=today,
        )

        Borrowing.objects.create(
            user=self.user,
            book=self.book,
            borrow_date=borrow_date,
            expected_return_date=today + timedelta(days=7),
        )

        Borrowing.objects.create(
            user=self.user,
            book=self.book,
            borrow_date=borrow_date,
            expected_return_date=today - timedelta(days=1),
            actual_return_date=today,
        )

        result = list(get_overdue_borrowings())

        self.assertEqual(
            [borrowing.pk for borrowing in result],
            [overdue.pk, due_today.pk],
        )

    def test_returns_empty_queryset_when_no_borrowings_are_overdue(
        self,
    ):
        self.assertFalse(get_overdue_borrowings().exists())
