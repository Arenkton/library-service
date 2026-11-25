from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from books.models import Book
from borrowings.models import Borrowing
from notifications.tasks import notify_overdue_borrowings


User = get_user_model()


class NotifyOverdueBorrowingsTests(TestCase):
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

    def create_borrowing(
        self,
        expected_return_date,
        actual_return_date=None,
    ):
        return Borrowing.objects.create(
            user=self.user,
            book=self.book,
            borrow_date=(
                timezone.localdate() - timedelta(days=14)
            ),
            expected_return_date=expected_return_date,
            actual_return_date=actual_return_date,
        )

    @patch("notifications.tasks.send_telegram_message")
    def test_sends_message_for_each_overdue_borrowing(
        self,
        mock_send,
    ):
        mock_send.return_value = True
        today = timezone.localdate()

        overdue = self.create_borrowing(
            today - timedelta(days=3)
        )
        due_today = self.create_borrowing(today)

        result = notify_overdue_borrowings.run()

        self.assertEqual(result, 2)
        self.assertEqual(mock_send.call_count, 2)

        messages = [
            call.args[0]
            for call in mock_send.call_args_list
        ]

        self.assertIn(
            f"Borrowing ID: {overdue.pk}",
            messages[0],
        )
        self.assertIn(
            f"Borrowing ID: {due_today.pk}",
            messages[1],
        )

        for message in messages:
            self.assertIn("Overdue borrowing!", message)
            self.assertIn(f"Book: {self.book.title}", message)
            self.assertIn(f"User ID: {self.user.pk}", message)
            self.assertIn("Expected return:", message)

    @patch("notifications.tasks.send_telegram_message")
    def test_sends_message_when_no_borrowings_are_overdue(
        self,
        mock_send,
    ):
        mock_send.return_value = True

        result = notify_overdue_borrowings.run()

        self.assertEqual(result, 0)
        mock_send.assert_called_once_with(
            "No borrowings overdue today!"
        )

    @patch("notifications.tasks.send_telegram_message")
    def test_ignores_returned_and_future_borrowings(
        self,
        mock_send,
    ):
        mock_send.return_value = True
        today = timezone.localdate()

        self.create_borrowing(
            today + timedelta(days=5)
        )

        self.create_borrowing(
            today - timedelta(days=2),
            actual_return_date=today,
        )

        result = notify_overdue_borrowings.run()

        self.assertEqual(result, 0)
        mock_send.assert_called_once_with(
            "No borrowings overdue today!"
        )

    @patch("notifications.tasks.send_telegram_message")
    def test_failed_notification_is_not_counted(
        self,
        mock_send,
    ):
        mock_send.return_value = False

        overdue = self.create_borrowing(
            timezone.localdate() - timedelta(days=2)
        )

        result = notify_overdue_borrowings.run()

        self.assertEqual(result, 0)
        mock_send.assert_called_once()

        message = mock_send.call_args.args[0]

        self.assertIn(
            f"Borrowing ID: {overdue.pk}",
            message,
        )
        self.assertNotIn(
            "No borrowings overdue today!",
            message,
        )
