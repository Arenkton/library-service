import hashlib
import hmac
import json
import time

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from books.models import Book
from borrowings.models import Borrowing
from payments.models import Payment


User = get_user_model()

TEST_WEBHOOK_SECRET = "whsec_test_dummy"


@override_settings(
    STRIPE_WEBHOOK_SECRET=TEST_WEBHOOK_SECRET,
)
class StripeWebhookTests(APITestCase):
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
        self.url = reverse("stripe-webhook")

    def make_event(
        self,
        event_type="checkout.session.completed",
        **session_overrides,
    ):
        session = {
            "id": self.payment.session_id,
            "object": "checkout.session",
            "status": "complete",
            "payment_status": "paid",
            "currency": "usd",
            "amount_total": 1050,
            "metadata": {
                "borrowing_id": str(self.borrowing.pk),
            },
        }

        session.update(session_overrides)

        return {
            "id": "evt_test_123",
            "object": "event",
            "type": event_type,
            "data": {
                "object": session,
            },
        }

    def send_signed_payload(
        self,
        payload,
        signature=None,
    ):
        timestamp = int(time.time())

        signed_payload = (
            f"{timestamp}.{payload}"
        ).encode("utf-8")

        digest = hmac.new(
            TEST_WEBHOOK_SECRET.encode("utf-8"),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()

        if signature is None:
            signature = (
                f"t={timestamp},v1={digest}"
            )

        return self.client.post(
            self.url,
            data=payload,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=signature,
        )

    def send_event(self, event):
        payload = json.dumps(event)
        return self.send_signed_payload(payload)

    def test_paid_event_marks_payment_as_paid(self):
        response = self.send_event(
            self.make_event()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["status"],
            "success",
        )

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PAID,
        )

    def test_async_payment_succeeded_marks_paid(self):
        response = self.send_event(
            self.make_event(
                event_type=(
                    "checkout.session."
                    "async_payment_succeeded"
                )
            )
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

    def test_unpaid_session_remains_pending(self):
        response = self.send_event(
            self.make_event(
                status="open",
                payment_status="unpaid",
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["status"],
            "not_paid",
        )

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PENDING,
        )

    def test_invalid_signature_is_rejected(self):
        payload = json.dumps(
            self.make_event()
        )

        response = self.send_signed_payload(
            payload,
            signature="t=123456,v1=invalid",
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

    def test_missing_signature_is_rejected(self):
        response = self.client.post(
            self.url,
            data=json.dumps(self.make_event()),
            content_type="application/json",
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

    @override_settings(STRIPE_WEBHOOK_SECRET="")
    def test_missing_secret_returns_503(self):
        with self.assertLogs(
            "payments.webhooks",
            level="ERROR",
        ):
            response = self.send_event(
                self.make_event()
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

    def test_incorrect_amount_is_rejected(self):
        with self.assertLogs(
            "payments.webhooks",
            level="ERROR",
        ):
            response = self.send_event(
                self.make_event(
                    amount_total=500,
                )
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

    def test_incorrect_borrowing_id_is_rejected(self):
        with self.assertLogs(
            "payments.webhooks",
            level="ERROR",
        ):
            response = self.send_event(
                self.make_event(
                    metadata={
                        "borrowing_id": "99999",
                    },
                )
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

    def test_duplicate_event_is_idempotent(self):
        event = self.make_event()

        with patch(
            "payments.webhooks.logger.info"
        ) as mock_logger:
            first_response = self.send_event(event)
            second_response = self.send_event(event)

        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            second_response.status_code,
            status.HTTP_200_OK,
        )

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PAID,
        )

        mock_logger.assert_called_once()

    def test_unrelated_event_is_ignored(self):
        response = self.send_event(
            self.make_event(
                event_type="payment_intent.created",
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["status"],
            "ignored",
        )

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PENDING,
        )

    def test_unknown_session_is_ignored(self):
        with self.assertLogs(
            "payments.webhooks",
            level="WARNING",
        ):
            response = self.send_event(
                self.make_event(
                    id="cs_test_unknown",
                )
            )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["status"],
            "ignored",
        )

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PENDING,
        )

    def test_invalid_json_is_rejected(self):
        response = self.send_signed_payload(
            "invalid-json"
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
