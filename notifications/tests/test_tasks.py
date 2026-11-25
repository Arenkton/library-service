from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from books.models import Book
from borrowings.models import Borrowing
from notifications.tasks import notify_new_borrowing


User = get_user_model()


class NotifyNewBorrowingTests(TestCase):
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

        cls.borrowing = Borrowing.objects.create(
            user=cls.user,
            book=cls.book,
            expected_return_date=(
                timezone.localdate() + timedelta(days=7)
            ),
        )

    @patch("notifications.tasks.send_telegram_message")
    def test_sends_notification_for_existing_borrowing(
        self,
        mock_send,
    ):
        mock_send.return_value = True

        result = notify_new_borrowing.run(self.borrowing.pk)

        self.assertTrue(result)
        mock_send.assert_called_once()

        message = mock_send.call_args.args[0]

        self.assertIn(
            "New borrowing created!",
            message,
        )
        self.assertIn(
            f"Borrowing ID: {self.borrowing.pk}",
            message,
        )
        self.assertIn(
            f"Book: {self.book.title}",
            message,
        )
        self.assertIn(
            f"User ID: {self.user.pk}",
            message,
        )
        self.assertIn(
            f"Borrow date: {self.borrowing.borrow_date}",
            message,
        )
        self.assertIn(
            f"Expected return: {self.borrowing.expected_return_date}",
            message,
        )

    @patch("notifications.tasks.send_telegram_message")
    def test_nonexistent_borrowing_does_not_send_notification(
        self,
        mock_send,
    ):
        result = notify_new_borrowing.run(999999)

        self.assertFalse(result)
        mock_send.assert_not_called()

    @patch("notifications.tasks.send_telegram_message")
    def test_returns_false_when_message_is_not_sent(
        self,
        mock_send,
    ):
        mock_send.return_value = False

        result = notify_new_borrowing.run(self.borrowing.pk)

        self.assertFalse(result)
        mock_send.assert_called_once()
