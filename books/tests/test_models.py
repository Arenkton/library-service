from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from books.models import Book


class BookModelTests(TestCase):
    def setUp(self):
        self.book = Book.objects.create(
            title="The Hobbit",
            author="J. R. R. Tolkien",
            cover=Book.CoverType.HARD,
            inventory=5,
            daily_fee=Decimal("1.50"),
        )

    def test_book_string_representation(self):
        self.assertEqual(
            str(self.book),
            "The Hobbit by J. R. R. Tolkien",
        )

    def test_zero_inventory_allowed(self):
        self.book.inventory = 0
        self.book.full_clean()

        self.assertEqual(self.book.inventory, 0)

    def test_invalid_cover(self):
        self.book.cover = "PAPER"

        with self.assertRaises(ValidationError):
            self.book.full_clean()

    def test_negative_inventory(self):
        self.book.inventory = -1

        with self.assertRaises(ValidationError):
            self.book.full_clean()

    def test_zero_daily_fee(self):
        self.book.daily_fee = Decimal("0.00")

        with self.assertRaises(ValidationError):
            self.book.full_clean()
