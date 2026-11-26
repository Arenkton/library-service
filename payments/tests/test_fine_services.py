from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from stripe import StripeError

from books.models import Book
from borrowings.models import Borrowing
from payments.models import Payment
from payments.services import create_fine_payment_for_borrowing


User = get_user_model()


@override_settings(
    STRIPE_SECRET_KEY="sk_test_dummy",
    STRIPE_SUCCESS_URL="http://localhost:8001/payments/success/",
    STRIPE_CANCEL_URL="http://localhost:8001/payments/cancel/",
    FINE_MULTIPLIER=Decimal("2"),
)
class FinePaymentServiceTests(TestCase):
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
            inventory=3,
            daily_fee=Decimal("1.50"),
        )

        today = timezone.localdate()

        cls.borrowing = Borrowing.objects.create(
            user=cls.user,
            book=cls.book,
            borrow_date=today - timedelta(days=10),
            expected_return_date=today - timedelta(days=3),
            actual_return_date=today,
        )

    @patch("payments.services.StripeClient")
    def test_overdue_borrowing_creates_fine(
        self,
        mock_client_class,
    ):
        mock_client = mock_client_class.return_value

        mock_session = (
            mock_client.v1.checkout.sessions.create.return_value
        )

        mock_session.id = "cs_test_fine_123"
        mock_session.url = (
            "https://checkout.stripe.com/fine-session"
        )

        payment = create_fine_payment_for_borrowing(
            self.borrowing
        )

        self.assertEqual(Payment.objects.count(), 1)

        self.assertEqual(
            payment.borrowing,
            self.borrowing,
        )
        self.assertEqual(
            payment.type,
            Payment.Type.FINE,
        )
        self.assertEqual(
            payment.status,
            Payment.Status.PENDING,
        )
        self.assertEqual(
            payment.money_to_pay,
            Decimal("9.00"),
        )
        self.assertEqual(
            payment.session_id,
            "cs_test_fine_123",
        )

        mock_client_class.assert_called_once_with(
            "sk_test_dummy"
        )

        mock_client.v1.checkout.sessions.create.assert_called_once_with(
            {
                "mode": "payment",
                "line_items": [
                    {
                        "price_data": {
                            "currency": "usd",
                            "unit_amount": 900,
                            "product_data": {
                                "name": "Overdue fine: The Hobbit",
                            },
                        },
                        "quantity": 1,
                    },
                ],
                "metadata": {
                    "borrowing_id": str(self.borrowing.pk),
                    "payment_type": Payment.Type.FINE,
                },
                "success_url": (
                    "http://localhost:8001/payments/success/"
                ),
                "cancel_url": (
                    "http://localhost:8001/payments/cancel/"
                ),
            },
            options={
                "idempotency_key": (
                    f"library-service-fine-{self.borrowing.pk}-v1"
                ),
            },
        )

    @patch("payments.services.StripeClient")
    def test_not_returned_borrowing_raises_error(
        self,
        mock_client_class,
    ):
        self.borrowing.actual_return_date = None

        self.borrowing.save(
            update_fields=["actual_return_date"]
        )

        with self.assertRaisesMessage(
            ValueError,
            "Borrowing must be returned",
        ):
            create_fine_payment_for_borrowing(
                self.borrowing
            )

        self.assertFalse(Payment.objects.exists())
        mock_client_class.assert_not_called()

    @patch("payments.services.StripeClient")
    def test_returned_on_time_has_no_fine(
        self,
        mock_client_class,
    ):
        self.borrowing.actual_return_date = (
            self.borrowing.expected_return_date
        )

        self.borrowing.save(
            update_fields=["actual_return_date"]
        )

        result = create_fine_payment_for_borrowing(
            self.borrowing
        )

        self.assertIsNone(result)
        self.assertFalse(Payment.objects.exists())
        mock_client_class.assert_not_called()

    @patch("payments.services.StripeClient")
    def test_existing_fine_is_reused(
        self,
        mock_client_class,
    ):
        existing_payment = Payment.objects.create(
            borrowing=self.borrowing,
            type=Payment.Type.FINE,
            status=Payment.Status.PENDING,
            session_url=(
                "https://checkout.stripe.com/existing-fine"
            ),
            session_id="cs_test_existing_fine",
            money_to_pay=Decimal("9.00"),
        )

        result = create_fine_payment_for_borrowing(
            self.borrowing
        )

        self.assertEqual(
            result.pk,
            existing_payment.pk,
        )

        self.assertEqual(Payment.objects.count(), 1)
        mock_client_class.assert_not_called()

    @patch("payments.services.StripeClient")
    def test_stripe_error_does_not_create_fine(
        self,
        mock_client_class,
    ):
        mock_client = mock_client_class.return_value

        mock_client.v1.checkout.sessions.create.side_effect = (
            StripeError("Stripe unavailable")
        )

        with self.assertRaises(StripeError):
            create_fine_payment_for_borrowing(
                self.borrowing
            )

        self.assertFalse(Payment.objects.exists())
