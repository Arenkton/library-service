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


class PaymentAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="reader@example.com",
            password="TestPassword123!",
        )

        cls.other_user = User.objects.create_user(
            email="another@example.com",
            password="TestPassword123!",
        )

        cls.admin = User.objects.create_user(
            email="admin@example.com",
            password="TestPassword123!",
            is_staff=True,
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

        cls.other_borrowing = Borrowing.objects.create(
            user=cls.other_user,
            book=cls.book,
            expected_return_date=(
                timezone.localdate() + timedelta(days=5)
            ),
        )

        cls.payment = Payment.objects.create(
            borrowing=cls.borrowing,
            type=Payment.Type.PAYMENT,
            session_url="https://checkout.stripe.com/test1",
            session_id="cs_test_111",
            money_to_pay=Decimal("10.50"),
        )

        cls.other_payment = Payment.objects.create(
            borrowing=cls.other_borrowing,
            type=Payment.Type.FINE,
            session_url="https://checkout.stripe.com/test2",
            session_id="cs_test_222",
            money_to_pay=Decimal("15.00"),
        )

        cls.list_url = reverse("payment-list")

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token

        self.client.credentials(
            HTTP_AUTHORIZE=f"Bearer {token}"
        )

    def test_user_sees_only_own_payments(self):
        self.authenticate(self.user)

        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["id"],
            self.payment.pk,
        )

    def test_user_can_retrieve_own_payment(self):
        self.authenticate(self.user)

        url = reverse(
            "payment-detail",
            args=[self.payment.pk],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["session_id"],
            "cs_test_111",
        )
        self.assertEqual(
            response.data["money_to_pay"],
            "10.50",
        )

    def test_user_cannot_retrieve_other_users_payment(self):
        self.authenticate(self.user)

        url = reverse(
            "payment-detail",
            args=[self.other_payment.pk],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_admin_can_list_all_payments(self):
        self.authenticate(self.admin)

        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        payment_ids = {
            payment["id"]
            for payment in response.data
        }

        self.assertEqual(
            payment_ids,
            {
                self.payment.pk,
                self.other_payment.pk,
            },
        )

    def test_admin_can_retrieve_any_payment(self):
        self.authenticate(self.admin)

        url = reverse(
            "payment-detail",
            args=[self.other_payment.pk],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["id"],
            self.other_payment.pk,
        )

    def test_unauthenticated_user_cannot_access_payments(self):
        list_response = self.client.get(self.list_url)

        detail_url = reverse(
            "payment-detail",
            args=[self.payment.pk],
        )
        detail_response = self.client.get(detail_url)

        self.assertEqual(
            list_response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            detail_response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_user_cannot_modify_payments(self):
        self.authenticate(self.user)

        detail_url = reverse(
            "payment-detail",
            args=[self.payment.pk],
        )

        responses = [
            self.client.post(
                self.list_url,
                {},
                format="json",
            ),
            self.client.patch(
                detail_url,
                {"status": Payment.Status.PAID},
                format="json",
            ),
            self.client.delete(detail_url),
        ]

        for response in responses:
            self.assertEqual(
                response.status_code,
                status.HTTP_405_METHOD_NOT_ALLOWED,
            )

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PENDING,
        )
