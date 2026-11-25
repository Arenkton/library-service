from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from stripe import StripeError

from books.models import Book
from borrowings.models import Borrowing
from payments.models import Payment


User = get_user_model()


@override_settings(
    STRIPE_SECRET_KEY="sk_test_dummy",
    STRIPE_SUCCESS_URL="http://localhost:8001/payments/success/",
    STRIPE_CANCEL_URL="http://localhost:8001/payments/cancel/",
)
class BorrowingPaymentIntegrationTests(APITestCase):
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
            inventory=2,
            daily_fee=Decimal("1.50"),
        )

    def setUp(self):
        token = RefreshToken.for_user(
            self.user
        ).access_token

        self.client.credentials(
            HTTP_AUTHORIZE=f"Bearer {token}"
        )

        self.url = reverse("borrowing-list")

    def borrowing_data(self):
        return {
            "book": self.book.pk,
            "expected_return_date": (
                timezone.localdate() + timedelta(days=7)
            ).isoformat(),
        }

    @patch("borrowings.views.notify_new_borrowing.delay")
    @patch("payments.services.StripeClient")
    def test_creating_borrowing_creates_payment(
        self,
        mock_client_class,
        mock_notify,
    ):
        mock_session = (
            mock_client_class.return_value
            .v1.checkout.sessions.create.return_value
        )
        mock_session.id = "cs_test_123"
        mock_session.url = (
            "https://checkout.stripe.com/test-session"
        )

        with self.captureOnCommitCallbacks(
            execute=True
        ) as callbacks:
            response = self.client.post(
                self.url,
                self.borrowing_data(),
                format="json",
            )

            mock_notify.assert_not_called()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(Borrowing.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)

        borrowing = Borrowing.objects.get()
        payment = Payment.objects.get()

        self.assertEqual(
            response.data["id"],
            borrowing.pk,
        )
        self.assertEqual(
            response.data["user"],
            self.user.pk,
        )
        self.assertEqual(
            response.data["book"]["title"],
            "The Hobbit",
        )

        payments = response.data["payments"]

        self.assertEqual(len(payments), 1)

        payment_data = payments[0]

        self.assertEqual(
            payment_data["id"],
            payment.pk,
        )
        self.assertEqual(
            payment_data["status"],
            Payment.Status.PENDING,
        )
        self.assertEqual(
            payment_data["money_to_pay"],
            "10.50",
        )
        self.assertEqual(
            payment_data["session_url"],
            "https://checkout.stripe.com/test-session",
        )
        self.assertEqual(
            payment_data["session_id"],
            "cs_test_123",
        )
        self.assertEqual(payment.borrowing, borrowing)
        self.assertEqual(
            payment.status,
            Payment.Status.PENDING,
        )
        self.assertEqual(
            payment.type,
            Payment.Type.PAYMENT,
        )
        self.assertEqual(
            payment.money_to_pay,
            Decimal("10.50"),
        )
        self.assertEqual(
            payment.session_id,
            "cs_test_123",
        )

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 1)

        mock_client_class.return_value.v1.checkout.sessions.create.assert_called_once()

        self.assertEqual(len(callbacks), 1)
        mock_notify.assert_called_once_with(
            borrowing.pk
        )

    @patch("borrowings.views.notify_new_borrowing.delay")
    @patch("payments.services.StripeClient")
    def test_stripe_failure_rolls_back_borrowing(
        self,
        mock_client_class,
        mock_notify,
    ):
        mock_client_class.return_value.v1.checkout.sessions.create.side_effect = (
            StripeError("Stripe unavailable")
        )

        with self.assertLogs(
            "borrowings.views",
            level="ERROR",
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ) as callbacks:
                response = self.client.post(
                    self.url,
                    self.borrowing_data(),
                    format="json",
                )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

        self.assertEqual(Borrowing.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 2)

        self.assertEqual(len(callbacks), 0)
        mock_notify.assert_not_called()

    @patch("borrowings.views.notify_new_borrowing.delay")
    @patch("payments.services.StripeClient")
    def test_invalid_date_does_not_call_stripe(
        self,
        mock_client_class,
        mock_notify,
    ):
        data = {
            "book": self.book.pk,
            "expected_return_date": (
                timezone.localdate() - timedelta(days=1)
            ).isoformat(),
        }

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertFalse(Borrowing.objects.exists())
        self.assertFalse(Payment.objects.exists())

        mock_client_class.assert_not_called()
        mock_notify.assert_not_called()

    @patch("borrowings.views.notify_new_borrowing.delay")
    @patch("payments.services.StripeClient")
    def test_out_of_stock_does_not_call_stripe(
        self,
        mock_client_class,
        mock_notify,
    ):
        self.book.inventory = 0
        self.book.save(update_fields=["inventory"])

        response = self.client.post(
            self.url,
            self.borrowing_data(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertFalse(Borrowing.objects.exists())
        self.assertFalse(Payment.objects.exists())

        mock_client_class.assert_not_called()
        mock_notify.assert_not_called()

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 0)
