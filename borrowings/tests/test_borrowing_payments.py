from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from books.models import Book
from borrowings.models import Borrowing
from payments.models import Payment


User = get_user_model()


class BorrowingPaymentsTests(APITestCase):
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

        cls.payment = Payment.objects.create(
            borrowing=cls.borrowing,
            type=Payment.Type.PAYMENT,
            session_url="https://checkout.stripe.com/test1",
            session_id="cs_test_111",
            money_to_pay=Decimal("10.50"),
        )

        cls.fine = Payment.objects.create(
            borrowing=cls.borrowing,
            type=Payment.Type.FINE,
            session_url="https://checkout.stripe.com/test2",
            session_id="cs_test_222",
            money_to_pay=Decimal("5.00"),
        )

        cls.borrowing_without_payments = (
            Borrowing.objects.create(
                user=cls.user,
                book=cls.book,
                expected_return_date=(
                    timezone.localdate() + timedelta(days=5)
                ),
            )
        )

    def setUp(self):
        token = RefreshToken.for_user(
            self.user
        ).access_token

        self.client.credentials(
            HTTP_AUTHORIZE=f"Bearer {token}"
        )

    def test_borrowing_detail_contains_payments(self):
        url = reverse(
            "borrowing-detail",
            args=[self.borrowing.pk],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        payments = response.data["payments"]

        self.assertEqual(len(payments), 2)

        payments_by_id = {
            payment["id"]: payment
            for payment in payments
        }

        regular_payment = payments_by_id[
            self.payment.pk
        ]
        fine_payment = payments_by_id[
            self.fine.pk
        ]

        self.assertEqual(
            regular_payment["type"],
            "PAYMENT",
        )
        self.assertEqual(
            regular_payment["status"],
            "PENDING",
        )
        self.assertEqual(
            regular_payment["money_to_pay"],
            "10.50",
        )
        self.assertEqual(
            regular_payment["session_id"],
            "cs_test_111",
        )

        self.assertEqual(
            fine_payment["type"],
            "FINE",
        )
        self.assertEqual(
            fine_payment["money_to_pay"],
            "5.00",
        )

    def test_borrowing_without_payments_returns_empty_list(
        self,
    ):
        url = reverse(
            "borrowing-detail",
            args=[self.borrowing_without_payments.pk],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["payments"],
            [],
        )
