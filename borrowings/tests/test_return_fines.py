from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from kombu.exceptions import OperationalError
from rest_framework import status
from rest_framework.test import APITestCase

from books.models import Book
from borrowings.models import Borrowing


User = get_user_model()


class BorrowingReturnFineTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="fine-reader@example.com",
            password="TestPassword123!",
        )

        cls.book = Book.objects.create(
            title="The Hobbit",
            author="J. R. R. Tolkien",
            cover="HARD",
            inventory=2,
            daily_fee=Decimal("1.50"),
        )

        today = timezone.localdate()

        cls.borrowing = Borrowing.objects.create(
            user=cls.user,
            book=cls.book,
            borrow_date=today - timedelta(days=10),
            expected_return_date=today - timedelta(days=3),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.url = reverse(
            "borrowing-return-book",
            kwargs={"pk": self.borrowing.pk},
        )

    @patch(
        "borrowings.views."
        "create_fine_for_returned_borrowing.delay"
    )
    def test_overdue_return_queues_fine(self, mock_delay):
        with self.captureOnCommitCallbacks(
            execute=True
        ) as callbacks:
            response = self.client.post(self.url)

            mock_delay.assert_not_called()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(callbacks), 1)

        mock_delay.assert_called_once_with(
            self.borrowing.pk
        )

        self.borrowing.refresh_from_db()
        self.book.refresh_from_db()

        self.assertEqual(
            self.borrowing.actual_return_date,
            timezone.localdate(),
        )
        self.assertEqual(self.book.inventory, 3)

    @patch(
        "borrowings.views."
        "create_fine_for_returned_borrowing.delay"
    )
    def test_on_time_return_does_not_queue_fine(
        self,
        mock_delay,
    ):
        self.borrowing.expected_return_date = (
            timezone.localdate() + timedelta(days=2)
        )
        self.borrowing.save(
            update_fields=["expected_return_date"]
        )

        with self.captureOnCommitCallbacks(
            execute=True
        ) as callbacks:
            response = self.client.post(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(callbacks), 0)

        mock_delay.assert_not_called()

        self.borrowing.refresh_from_db()
        self.book.refresh_from_db()

        self.assertEqual(
            self.borrowing.actual_return_date,
            timezone.localdate(),
        )
        self.assertEqual(self.book.inventory, 3)

    @patch(
        "borrowings.views."
        "create_fine_for_returned_borrowing.delay"
    )
    def test_return_twice_does_not_duplicate_fine(
        self,
        mock_delay,
    ):
        with self.captureOnCommitCallbacks(
            execute=True
        ) as callbacks:
            first_response = self.client.post(self.url)
            second_response = self.client.post(self.url)

        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            second_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(len(callbacks), 1)
        mock_delay.assert_called_once_with(
            self.borrowing.pk
        )

        self.book.refresh_from_db()

        self.assertEqual(self.book.inventory, 3)

    @patch(
        "borrowings.views."
        "create_fine_for_returned_borrowing.delay"
    )
    def test_redis_failure_does_not_cancel_return(
        self,
        mock_delay,
    ):
        mock_delay.side_effect = OperationalError(
            "Redis unavailable"
        )

        with self.assertLogs(
            "borrowings.views",
            level="ERROR",
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ) as callbacks:
                response = self.client.post(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(callbacks), 1)

        self.borrowing.refresh_from_db()
        self.book.refresh_from_db()

        self.assertEqual(
            self.borrowing.actual_return_date,
            timezone.localdate(),
        )
        self.assertEqual(self.book.inventory, 3)

        mock_delay.assert_called_once_with(
            self.borrowing.pk
        )

    @patch(
        "borrowings.views."
        "create_fine_for_returned_borrowing.delay"
    )
    def test_unauthorized_user_cannot_return_book(
        self,
        mock_delay,
    ):
        self.client.force_authenticate(user=None)

        response = self.client.post(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        self.borrowing.refresh_from_db()
        self.book.refresh_from_db()

        self.assertIsNone(
            self.borrowing.actual_return_date
        )
        self.assertEqual(self.book.inventory, 2)

        mock_delay.assert_not_called()
