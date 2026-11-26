from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from kombu.exceptions import OperationalError

from books.models import Book
from borrowings.models import Borrowing
from payments.models import Payment
from payments.tasks import enqueue_missing_fines


User = get_user_model()


class MissingFineRecoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="recovery-reader@example.com",
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
        expected_offset=-3,
        actual_offset=0,
    ):
        today = timezone.localdate()

        actual_return_date = None
        if actual_offset is not None:
            actual_return_date = (
                today + timedelta(days=actual_offset)
            )

        return Borrowing.objects.create(
            user=self.user,
            book=self.book,
            borrow_date=today - timedelta(days=14),
            expected_return_date=(
                today + timedelta(days=expected_offset)
            ),
            actual_return_date=actual_return_date,
        )

    def create_payment(
        self,
        borrowing,
        payment_type,
        session_id,
    ):
        return Payment.objects.create(
            borrowing=borrowing,
            type=payment_type,
            status=Payment.Status.PENDING,
            session_id=session_id,
            session_url=(
                f"https://checkout.stripe.com/{session_id}"
            ),
            money_to_pay=Decimal("9.00"),
        )

    @patch(
        "payments.tasks."
        "create_fine_for_returned_borrowing.delay"
    )
    def test_overdue_borrowing_without_fine_is_queued(
        self,
        mock_delay,
    ):
        borrowing = self.create_borrowing()

        result = enqueue_missing_fines()

        self.assertEqual(result, 1)
        mock_delay.assert_called_once_with(
            borrowing.pk
        )

    @patch(
        "payments.tasks."
        "create_fine_for_returned_borrowing.delay"
    )
    def test_active_and_on_time_borrowings_are_ignored(
        self,
        mock_delay,
    ):
        self.create_borrowing(
            actual_offset=None,
        )

        self.create_borrowing(
            expected_offset=-3,
            actual_offset=-3,
        )

        result = enqueue_missing_fines()

        self.assertEqual(result, 0)
        mock_delay.assert_not_called()

    @patch(
        "payments.tasks."
        "create_fine_for_returned_borrowing.delay"
    )
    def test_existing_fine_is_not_queued_again(
        self,
        mock_delay,
    ):
        borrowing = self.create_borrowing()

        self.create_payment(
            borrowing=borrowing,
            payment_type=Payment.Type.FINE,
            session_id="cs_test_existing_fine",
        )

        result = enqueue_missing_fines()

        self.assertEqual(result, 0)
        mock_delay.assert_not_called()

    @patch(
        "payments.tasks."
        "create_fine_for_returned_borrowing.delay"
    )
    def test_regular_payment_does_not_prevent_fine(
        self,
        mock_delay,
    ):
        borrowing = self.create_borrowing()

        self.create_payment(
            borrowing=borrowing,
            payment_type=Payment.Type.PAYMENT,
            session_id="cs_test_regular_payment",
        )

        result = enqueue_missing_fines()

        self.assertEqual(result, 1)
        mock_delay.assert_called_once_with(
            borrowing.pk
        )

    @patch(
        "payments.tasks."
        "create_fine_for_returned_borrowing.delay"
    )
    def test_redis_error_stops_processing(
        self,
        mock_delay,
    ):
        self.create_borrowing()
        self.create_borrowing()

        mock_delay.side_effect = [
            None,
            OperationalError("Redis unavailable"),
        ]

        with self.assertLogs(
            "payments.tasks",
            level="ERROR",
        ):
            result = enqueue_missing_fines()

        self.assertEqual(result, 1)
        self.assertEqual(mock_delay.call_count, 2)
