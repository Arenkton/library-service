from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from books.models import Book
from borrowings.models import Borrowing
from payments.models import Payment
from payments.services import create_payment_for_borrowing


User = get_user_model()


@override_settings(
    STRIPE_SECRET_KEY="sk_test_dummy",
    STRIPE_SUCCESS_URL="http://localhost:8001/payments/success/",
    STRIPE_CANCEL_URL="http://localhost:8001/payments/cancel/",
)
class CreatePaymentForBorrowingTests(TestCase):
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

    @patch("payments.services.StripeClient")
    def test_creates_stripe_session_and_payment(
        self,
        mock_client_class,
    ):
        mock_client = mock_client_class.return_value

        mock_session = (
            mock_client.v1.checkout.sessions.create.return_value
        )

        mock_session.id = "cs_test_123"
        mock_session.url = (
            "https://checkout.stripe.com/test-session"
        )

        payment = create_payment_for_borrowing(
            self.borrowing
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
                            "unit_amount": 1050,
                            "product_data": {
                                "name": "The Hobbit",
                            },
                        },
                        "quantity": 1,
                    },
                ],
                "metadata": {
                    "borrowing_id": str(
                        self.borrowing.pk
                    ),
                },
                "success_url": (
                    "http://localhost:8001/payments/success/"
                ),
                "cancel_url": (
                    "http://localhost:8001/payments/cancel/"
                ),
            }
        )

        self.assertEqual(
            Payment.objects.count(),
            1,
        )

        self.assertEqual(
            payment.borrowing,
            self.borrowing,
        )
        self.assertEqual(
            payment.type,
            Payment.Type.PAYMENT,
        )
        self.assertEqual(
            payment.status,
            Payment.Status.PENDING,
        )
        self.assertEqual(
            payment.money_to_pay,
            Decimal("10.50"),
        )
        self.assertEqual(
            payment.session_id,
            "cs_test_123",
        )
        self.assertEqual(
            payment.session_url,
            "https://checkout.stripe.com/test-session",
        )

    @patch("payments.services.StripeClient")
    def test_rejects_invalid_borrowing_duration(
        self,
        mock_client_class,
    ):
        self.borrowing.expected_return_date = (
            self.borrowing.borrow_date
        )

        with self.assertRaisesMessage(
            ValueError,
            "Borrowing duration must be positive.",
        ):
            create_payment_for_borrowing(
                self.borrowing
            )

        mock_client_class.assert_not_called()

        self.assertFalse(
            Payment.objects.exists()
        )

    @patch("payments.services.StripeClient")
    def test_stripe_error_does_not_create_payment(
        self,
        mock_client_class,
    ):
        mock_client = mock_client_class.return_value

        mock_client.v1.checkout.sessions.create.side_effect = (
            RuntimeError("Stripe unavailable")
        )

        with self.assertRaisesMessage(
            RuntimeError,
            "Stripe unavailable",
        ):
            create_payment_for_borrowing(
                self.borrowing
            )

        self.assertFalse(
            Payment.objects.exists()
        )
