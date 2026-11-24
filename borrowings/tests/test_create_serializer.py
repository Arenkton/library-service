from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from books.models import Book
from borrowings.serializers import BorrowingCreateSerializer


class BorrowingCreateSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.book = Book.objects.create(
            title="Dune",
            author="Frank Herbert",
            cover="SOFT",
            inventory=5,
            daily_fee=Decimal("2.50"),
        )

    def setUp(self):
        self.valid_data = {
            "book": self.book.pk,
            "expected_return_date": (
                timezone.localdate() + timedelta(days=7)
            ).isoformat(),
        }

    def test_future_return_date_is_valid(self):
        serializer = BorrowingCreateSerializer(
            data=self.valid_data
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

    def test_today_return_date_is_invalid(self):
        self.valid_data["expected_return_date"] = (
            timezone.localdate().isoformat()
        )

        serializer = BorrowingCreateSerializer(
            data=self.valid_data
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn(
            "expected_return_date",
            serializer.errors,
        )

    def test_past_return_date_is_invalid(self):
        yesterday = (
            timezone.localdate() - timedelta(days=1)
        )

        self.valid_data["expected_return_date"] = (
            yesterday.isoformat()
        )

        serializer = BorrowingCreateSerializer(
            data=self.valid_data
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn(
            "expected_return_date",
            serializer.errors,
        )

    def test_book_is_required(self):
        self.valid_data.pop("book")

        serializer = BorrowingCreateSerializer(
            data=self.valid_data
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("book", serializer.errors)
