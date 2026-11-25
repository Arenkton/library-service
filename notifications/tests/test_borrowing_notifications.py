from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from books.models import Book
from borrowings.models import Borrowing

from kombu.exceptions import OperationalError

User = get_user_model()


class BorrowingNotificationTests(APITestCase):
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

    def setUp(self):
        token = RefreshToken.for_user(
            self.user
        ).access_token

        self.client.credentials(
            HTTP_AUTHORIZE=f"Bearer {token}"
        )

        self.url = reverse("borrowing-list")

        payment_patcher = patch(
            "borrowings.views.create_payment_for_borrowing"
        )

        self.mock_create_payment = payment_patcher.start()
        self.addCleanup(payment_patcher.stop)

    @patch("borrowings.views.notify_new_borrowing.delay")
    def test_successful_borrowing_queues_notification(
        self,
        mock_delay,
    ):
        data = {
            "book": self.book.pk,
            "expected_return_date": (
                timezone.localdate() + timedelta(days=7)
            ).isoformat(),
        }

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.post(
                self.url,
                data,
                format="json",
            )

            self.assertEqual(
                response.status_code,
                status.HTTP_201_CREATED,
            )
            mock_delay.assert_not_called()

        self.assertEqual(len(callbacks), 1)

        borrowing = Borrowing.objects.get(user=self.user)

        mock_delay.assert_called_once_with(borrowing.pk)

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 2)

    @patch("borrowings.views.notify_new_borrowing.delay")
    def test_invalid_borrowing_does_not_queue_notification(
        self,
        mock_delay,
    ):
        data = {
            "book": self.book.pk,
            "expected_return_date": (
                timezone.localdate() - timedelta(days=1)
            ).isoformat(),
        }

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.post(
                self.url,
                data,
                format="json",
            )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(len(callbacks), 0)
        mock_delay.assert_not_called()

        self.assertFalse(
            Borrowing.objects.filter(user=self.user).exists()
        )

    @patch("borrowings.views.notify_new_borrowing.delay")
    def test_out_of_stock_book_does_not_queue_notification(
        self,
        mock_delay,
    ):
        self.book.inventory = 0
        self.book.save(update_fields=["inventory"])

        data = {
            "book": self.book.pk,
            "expected_return_date": (
                timezone.localdate() + timedelta(days=7)
            ).isoformat(),
        }

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.post(
                self.url,
                data,
                format="json",
            )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(len(callbacks), 0)
        mock_delay.assert_not_called()

        self.assertFalse(
            Borrowing.objects.filter(user=self.user).exists()
        )

    @patch("borrowings.views.notify_new_borrowing.delay")
    def test_borrowing_succeeds_when_redis_is_unavailable(
        self,
        mock_delay,
    ):
        mock_delay.side_effect = OperationalError(
            "Redis connection failed"
        )

        data = {
            "book": self.book.pk,
            "expected_return_date": (
                timezone.localdate() + timedelta(days=7)
            ).isoformat(),
        }

        with self.assertLogs(
            "borrowings.views",
            level="ERROR",
        ) as captured_logs:
            with self.captureOnCommitCallbacks(
                execute=True
            ) as callbacks:
                response = self.client.post(
                    self.url,
                    data,
                    format="json",
                )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(len(callbacks), 1)

        borrowing = Borrowing.objects.get(
            user=self.user
        )

        mock_delay.assert_called_once_with(
            borrowing.pk
        )

        self.book.refresh_from_db()

        self.assertEqual(
            self.book.inventory,
            2,
        )

        self.assertIn(
            "Failed to queue notification",
            captured_logs.output[0],
        )
