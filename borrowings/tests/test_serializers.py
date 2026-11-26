from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from books.models import Book
from borrowings.models import Borrowing
from borrowings.serializers import BorrowingReadSerializer


User = get_user_model()


class BorrowingSerializerTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()

        self.user = User.objects.create_user(
            email="reader@example.com",
            password="TestPassword123!",
        )

        self.book = Book.objects.create(
            title="Dune",
            author="Frank Herbert",
            cover="SOFT",
            inventory=3,
            daily_fee=Decimal("2.50"),
        )

        self.borrowing = Borrowing.objects.create(
            user=self.user,
            book=self.book,
            expected_return_date=self.today + timedelta(days=10),
        )

    def test_serializer_contains_expected_fields(self):
        data = BorrowingReadSerializer(self.borrowing).data

        expected_fields = {
            "id",
            "borrow_date",
            "expected_return_date",
            "actual_return_date",
            "book",
            "user",
            "is_active",
            "payments",
        }

        self.assertEqual(set(data.keys()), expected_fields)
        self.assertEqual(data["payments"], [])

    def test_book_is_nested_object(self):
        data = BorrowingReadSerializer(self.borrowing).data

        self.assertIsInstance(data["book"], dict)
        self.assertEqual(data["book"]["id"], self.book.id)
        self.assertEqual(data["book"]["title"], "Dune")
        self.assertEqual(
            data["book"]["author"],
            "Frank Herbert",
        )

    def test_nested_book_contains_required_fields(self):
        data = BorrowingReadSerializer(self.borrowing).data

        expected_fields = {
            "id",
            "title",
            "author",
            "cover",
            "inventory",
            "daily_fee",
        }

        self.assertEqual(
            set(data["book"].keys()),
            expected_fields,
        )

    def test_user_is_serialized_as_id(self):
        data = BorrowingReadSerializer(self.borrowing).data

        self.assertEqual(data["user"], self.user.id)

    def test_active_borrowing_serialization(self):
        data = BorrowingReadSerializer(self.borrowing).data

        self.assertTrue(data["is_active"])
        self.assertIsNone(data["actual_return_date"])

    def test_returned_borrowing_serialization(self):
        self.borrowing.actual_return_date = self.today
        self.borrowing.save()

        data = BorrowingReadSerializer(self.borrowing).data

        self.assertFalse(data["is_active"])
        self.assertEqual(
            data["actual_return_date"],
            self.today.isoformat(),
        )

    def test_dates_are_iso_formatted(self):
        data = BorrowingReadSerializer(self.borrowing).data

        self.assertEqual(
            data["borrow_date"],
            self.today.isoformat(),
        )
        self.assertEqual(
            data["expected_return_date"],
            (self.today + timedelta(days=10)).isoformat(),
        )
