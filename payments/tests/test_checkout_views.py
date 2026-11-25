from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase
from stripe import StripeError

from books.models import Book
from borrowings.models import Borrowing
from payments.models import Payment


User = get_user_model()


@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
class PaymentCheckoutViewsTests(APITestCase):
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
            status=Payment.Status.PENDING,
            session_url=(
                "https://checkout.stripe.com/test-session"
            ),
            session_id="cs_test_123",
            money_to_pay=Decimal("10.50"),
        )

    def setUp(self):
        self.success_url = reverse("payment-success")
        self.cancel_url = reverse("payment-cancel")

    def mock_stripe_session(
        self,
        mock_client_class,
        **overrides,
    ):
        session_data = {
            "id": self.payment.session_id,
            "status": "complete",
            "payment_status": "paid",
            "currency": "usd",
            "amount_total": 1050,
            "metadata": {
                "borrowing_id": str(self.borrowing.pk),
            },
        }

        session_data.update(overrides)

        session = SimpleNamespace(**session_data)

        (
            mock_client_class.return_value
            .v1.checkout.sessions.retrieve.return_value
        ) = session

    @patch("payments.views.StripeClient")
    def test_success_marks_payment_as_paid(
        self,
        mock_client_class,
    ):
        self.mock_stripe_session(mock_client_class)

        response = self.client.get(
            self.success_url,
            {"session_id": self.payment.session_id},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PAID,
        )
        self.assertEqual(
            response.data["status"],
            Payment.Status.PAID,
        )

        (
            mock_client_class.return_value
            .v1.checkout.sessions.retrieve
            .assert_called_once_with(
                self.payment.session_id
            )
        )

    @patch("payments.views.StripeClient")
    def test_unpaid_session_remains_pending(
        self,
        mock_client_class,
    ):
        self.mock_stripe_session(
            mock_client_class,
            status="open",
            payment_status="unpaid",
        )

        response = self.client.get(
            self.success_url,
            {"session_id": self.payment.session_id},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PENDING,
        )
        self.assertEqual(
            response.data["status"],
            Payment.Status.PENDING,
        )

    @patch("payments.views.StripeClient")
    def test_incorrect_amount_does_not_confirm_payment(
        self,
        mock_client_class,
    ):
        self.mock_stripe_session(
            mock_client_class,
            amount_total=500,
        )

        response = self.client.get(
            self.success_url,
            {"session_id": self.payment.session_id},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PENDING,
        )

    @patch("payments.views.StripeClient")
    def test_incorrect_borrowing_id_is_rejected(
        self,
        mock_client_class,
    ):
        self.mock_stripe_session(
            mock_client_class,
            metadata={"borrowing_id": "99999"},
        )

        response = self.client.get(
            self.success_url,
            {"session_id": self.payment.session_id},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PENDING,
        )

    @patch("payments.views.StripeClient")
    def test_missing_session_id_returns_400(
        self,
        mock_client_class,
    ):
        response = self.client.get(
            self.success_url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        mock_client_class.assert_not_called()

    @patch("payments.views.StripeClient")
    def test_stripe_error_returns_503(
        self,
        mock_client_class,
    ):
        (
            mock_client_class.return_value
            .v1.checkout.sessions.retrieve.side_effect
        ) = StripeError("Stripe unavailable")

        response = self.client.get(
            self.success_url,
            {"session_id": self.payment.session_id},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PENDING,
        )

    def test_cancel_does_not_change_payment_status(self):
        response = self.client.get(
            self.cancel_url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertIn(
            "canceled",
            response.data["message"],
        )

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PENDING,
        )
