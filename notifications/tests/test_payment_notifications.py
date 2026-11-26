from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from celery.exceptions import Retry
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from books.models import Book
from borrowings.models import Borrowing
from notifications.tasks import notify_successful_payment
from notifications.telegram import TelegramTemporaryError
from payments.models import Payment


User = get_user_model()


class SuccessfulPaymentNotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="telegram-payment@example.com",
            password="TestPassword123!",
        )

        cls.book = Book.objects.create(
            title="The Hobbit",
            author="J. R. R. Tolkien",
            cover="HARD",
            inventory=3,
            daily_fee=Decimal("1.50"),
        )

        cls.borrowing = Borrowing.objects.create(
            user=cls.user,
            book=cls.book,
            expected_return_date=(
                timezone.localdate() + timedelta(days=7)
            ),
        )

        cls.payment = Payment.objects.create(
            borrowing=cls.borrowing,
            type=Payment.Type.PAYMENT,
            status=Payment.Status.PAID,
            session_id="cs_test_telegram_payment",
            session_url=(
                "https://checkout.stripe.com/test-payment"
            ),
            money_to_pay=Decimal("10.50"),
        )

    @patch("notifications.tasks.send_telegram_message")
    def test_paid_payment_sends_notification(
        self,
        mock_send,
    ):
        mock_send.return_value = True

        result = notify_successful_payment(
            self.payment.pk
        )

        self.assertTrue(result)

        expected_message = (
            "✅ Payment received!\n\n"
            f"Payment ID: {self.payment.pk}\n"
            "Type: Payment\n"
            f"Borrowing ID: {self.borrowing.pk}\n"
            "Book: The Hobbit\n"
            f"User ID: {self.user.pk}\n"
            "Amount: $10.50"
        )

        mock_send.assert_called_once_with(
            expected_message
        )

    @patch("notifications.tasks.send_telegram_message")
    def test_paid_fine_sends_notification(
        self,
        mock_send,
    ):
        mock_send.return_value = True

        fine = Payment.objects.create(
            borrowing=self.borrowing,
            type=Payment.Type.FINE,
            status=Payment.Status.PAID,
            session_id="cs_test_telegram_fine",
            session_url=(
                "https://checkout.stripe.com/test-fine"
            ),
            money_to_pay=Decimal("9.00"),
        )

        result = notify_successful_payment(fine.pk)

        self.assertTrue(result)

        message = mock_send.call_args.args[0]

        self.assertIn("Type: Fine", message)
        self.assertIn("Amount: $9.00", message)
        self.assertIn(
            f"Payment ID: {fine.pk}",
            message,
        )

        mock_send.assert_called_once()

    @patch("notifications.tasks.send_telegram_message")
    def test_pending_payment_is_ignored(
        self,
        mock_send,
    ):
        self.payment.status = Payment.Status.PENDING
        self.payment.save(update_fields=["status"])

        result = notify_successful_payment(
            self.payment.pk
        )

        self.assertFalse(result)
        mock_send.assert_not_called()

    @patch("notifications.tasks.send_telegram_message")
    def test_missing_payment_is_ignored(
        self,
        mock_send,
    ):
        result = notify_successful_payment(999999)

        self.assertFalse(result)
        mock_send.assert_not_called()

    @patch("notifications.tasks.send_telegram_message")
    def test_temporary_telegram_error_triggers_retry(
        self,
        mock_send,
    ):
        mock_send.side_effect = TelegramTemporaryError(
            "Telegram temporarily unavailable"
        )

        task = notify_successful_payment._get_current_object()

        with patch.object(
            task,
            "retry",
            side_effect=Retry(),
        ) as mock_retry:
            with self.assertRaises(Retry):
                task(self.payment.pk)

        mock_send.assert_called_once()
        mock_retry.assert_called_once()

        self.assertIsInstance(
            mock_retry.call_args.kwargs["exc"],
            TelegramTemporaryError,
        )
