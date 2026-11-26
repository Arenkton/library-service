from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from celery.exceptions import Retry
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from stripe import StripeError

from books.models import Book
from borrowings.models import Borrowing
from payments.tasks import create_fine_for_returned_borrowing


User = get_user_model()


class CreateFineTaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="task-reader@example.com",
            password="TestPassword123!",
        )

        cls.book = Book.objects.create(
            title="Clean Code",
            author="Robert C. Martin",
            cover="SOFT",
            inventory=3,
            daily_fee=Decimal("2.00"),
        )

        today = timezone.localdate()

        cls.borrowing = Borrowing.objects.create(
            user=cls.user,
            book=cls.book,
            borrow_date=today - timedelta(days=10),
            expected_return_date=today - timedelta(days=2),
            actual_return_date=today,
        )

    @patch(
        "payments.tasks."
        "create_fine_payment_for_borrowing"
    )
    def test_task_creates_fine(self, mock_service):
        mock_service.return_value = object()

        result = create_fine_for_returned_borrowing(
            self.borrowing.pk
        )

        self.assertTrue(result)

        mock_service.assert_called_once_with(
            self.borrowing
        )

    @patch(
        "payments.tasks."
        "create_fine_payment_for_borrowing"
    )
    def test_missing_borrowing_returns_false(
        self,
        mock_service,
    ):
        result = create_fine_for_returned_borrowing(
            999999
        )

        self.assertFalse(result)
        mock_service.assert_not_called()

    @patch(
        "payments.tasks."
        "create_fine_payment_for_borrowing"
    )
    def test_not_returned_borrowing_is_ignored(
        self,
        mock_service,
    ):
        self.borrowing.actual_return_date = None
        self.borrowing.save(
            update_fields=["actual_return_date"]
        )

        result = create_fine_for_returned_borrowing(
            self.borrowing.pk
        )

        self.assertFalse(result)
        mock_service.assert_not_called()

    @patch(
        "payments.tasks."
        "create_fine_payment_for_borrowing"
    )
    def test_no_fine_returns_false(self, mock_service):
        mock_service.return_value = None

        result = create_fine_for_returned_borrowing(
            self.borrowing.pk
        )

        self.assertFalse(result)
        mock_service.assert_called_once()

    @patch(
        "payments.tasks."
        "create_fine_payment_for_borrowing"
    )
    def test_stripe_error_triggers_retry(
        self,
        mock_service,
    ):
        mock_service.side_effect = StripeError(
            "Stripe temporarily unavailable"
        )

        task = (
            create_fine_for_returned_borrowing
            ._get_current_object()
        )

        with patch.object(
            task,
            "retry",
            side_effect=Retry(),
        ) as mock_retry:
            with self.assertRaises(Retry):
                task(self.borrowing.pk)

        mock_service.assert_called_once()
        mock_retry.assert_called_once()

        self.assertIsInstance(
            mock_retry.call_args.kwargs["exc"],
            StripeError,
        )
