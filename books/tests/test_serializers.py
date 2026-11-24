from django.test import TestCase

from books.serializers import BookSerializer


class BookSerializerTests(TestCase):
    def setUp(self):
        self.valid_data = {
            "title": "The Hobbit",
            "author": "J. R. R. Tolkien",
            "cover": "HARD",
            "inventory": 5,
            "daily_fee": "1.50",
        }

    def test_valid_book_data(self):
        serializer = BookSerializer(data=self.valid_data)

        self.assertTrue(serializer.is_valid())
        self.assertEqual(
            serializer.validated_data["title"],
            "The Hobbit",
        )

    def test_invalid_cover(self):
        self.valid_data["cover"] = "PAPER"

        serializer = BookSerializer(data=self.valid_data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("cover", serializer.errors)

    def test_negative_inventory(self):
        self.valid_data["inventory"] = -5

        serializer = BookSerializer(data=self.valid_data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("inventory", serializer.errors)

    def test_zero_inventory_allowed(self):
        self.valid_data["inventory"] = 0

        serializer = BookSerializer(data=self.valid_data)

        self.assertTrue(serializer.is_valid())

    def test_zero_daily_fee(self):
        self.valid_data["daily_fee"] = "0.00"

        serializer = BookSerializer(data=self.valid_data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("daily_fee", serializer.errors)

    def test_invalid_decimal_precision(self):
        self.valid_data["daily_fee"] = "1.999"

        serializer = BookSerializer(data=self.valid_data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("daily_fee", serializer.errors)

    def test_missing_title(self):
        self.valid_data.pop("title")

        serializer = BookSerializer(data=self.valid_data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("title", serializer.errors)
