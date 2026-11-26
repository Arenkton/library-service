import hashlib
import hmac
import json
import time

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from kombu.exceptions import OperationalError
from rest_framework import status
from rest_framework.test import APITestCase

from books.models import Book
from borrowings.models import Borrowing
from payments.models import Payment


User = get_user_model()
TEST_WEBHOOK_SECRET = "whsec_test_notifications"


@override_settings(
    STRIPE_WEBHOOK_SECRET=TEST_WEBHOOK_SECRET,
    STRIPE_SECRET_KEY="sk_test_dummy",
)
class PaymentNotificationIntegrationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="payment-notify@example.com",
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
            session_id="cs_test_notification_123",
            session_url=(
                "https://checkout.stripe.com/test-notification"
            ),
            money_to_pay=Decimal("10.50"),
        )

    def setUp(self):
        self.webhook_url = reverse("stripe-webhook")
        self.success_url = reverse("payment-success")

        webhook_patcher = patch(
            "payments.webhooks.notify_successful_payment"
        )
        mocked_webhook_task = webhook_patcher.start()
        self.mock_webhook_notification = (
            mocked_webhook_task.delay
        )
        self.addCleanup(webhook_patcher.stop)

        success_patcher = patch(
            "payments.views.notify_successful_payment"
        )
        mocked_success_task = success_patcher.start()
        self.mock_success_notification = (
            mocked_success_task.delay
        )
        self.addCleanup(success_patcher.stop)

    def send_webhook(self):
        event = {
            "id": "evt_test_notification",
            "object": "event",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": self.payment.session_id,
                    "object": "checkout.session",
                    "status": "complete",
                    "payment_status": "paid",
                    "currency": "usd",
                    "amount_total": 1050,
                    "metadata": {
                        "borrowing_id": str(
                            self.borrowing.pk
                        ),
                    },
                },
            },
        }

        payload = json.dumps(event)
        timestamp = int(time.time())

        signed_payload = (
            f"{timestamp}.{payload}"
        ).encode("utf-8")

        signature = hmac.new(
            TEST_WEBHOOK_SECRET.encode("utf-8"),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()

        return self.client.post(
            self.webhook_url,
            data=payload,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=(
                f"t={timestamp},v1={signature}"
            ),
        )

    def configure_stripe_mock(self, mock_client_class):
        mock_session = SimpleNamespace(
            id=self.payment.session_id,
            status="complete",
            payment_status="paid",
            currency="usd",
            amount_total=1050,
            metadata={
                "borrowing_id": str(self.borrowing.pk),
            },
        )

        mock_client = mock_client_class.return_value

        mock_client.v1.checkout.sessions.retrieve.return_value = (
            mock_session
        )

    def send_success_request(self):
        return self.client.get(
            self.success_url,
            {"session_id": self.payment.session_id},
        )

    def test_webhook_queues_notification_once(self):
        with self.captureOnCommitCallbacks(
            execute=True
        ) as callbacks:
            first_response = self.send_webhook()
            second_response = self.send_webhook()

            self.mock_webhook_notification.assert_not_called()

        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            second_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(callbacks), 1)

        self.mock_webhook_notification.assert_called_once_with(
            self.payment.pk
        )
        self.mock_success_notification.assert_not_called()

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PAID,
        )

    @patch("payments.views.StripeClient")
    def test_success_view_queues_notification_once(
        self,
        mock_client_class,
    ):
        self.configure_stripe_mock(mock_client_class)

        with self.captureOnCommitCallbacks(
            execute=True
        ) as callbacks:
            first_response = self.send_success_request()
            second_response = self.send_success_request()

        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            second_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(callbacks), 1)

        self.mock_success_notification.assert_called_once_with(
            self.payment.pk
        )
        self.mock_webhook_notification.assert_not_called()

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PAID,
        )

    @patch("payments.views.StripeClient")
    def test_webhook_and_success_do_not_duplicate_notification(
        self,
        mock_client_class,
    ):
        self.configure_stripe_mock(mock_client_class)

        with self.captureOnCommitCallbacks(
            execute=True
        ) as callbacks:
            webhook_response = self.send_webhook()
            success_response = self.send_success_request()

        self.assertEqual(
            webhook_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            success_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(callbacks), 1)

        self.mock_webhook_notification.assert_called_once_with(
            self.payment.pk
        )
        self.mock_success_notification.assert_not_called()

    def test_webhook_redis_error_does_not_undo_payment(self):
        self.mock_webhook_notification.side_effect = (
            OperationalError("Redis unavailable")
        )

        with self.assertLogs(
            "payments.webhooks",
            level="ERROR",
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.send_webhook()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PAID,
        )
        self.mock_webhook_notification.assert_called_once()

    @patch("payments.views.StripeClient")
    def test_success_redis_error_does_not_undo_payment(
        self,
        mock_client_class,
    ):
        self.configure_stripe_mock(mock_client_class)

        self.mock_success_notification.side_effect = (
            OperationalError("Redis unavailable")
        )

        with self.assertLogs(
            "payments.views",
            level="ERROR",
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.send_success_request()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PAID,
        )
        self.mock_success_notification.assert_called_once()
