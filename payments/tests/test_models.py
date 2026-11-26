from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from books.models import Book
from borrowings.models import Borrowing
from payments.models import Payment


User = get_user_model()


class PaymentModelTests(TestCase):
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

    def create_payment(self, **kwargs):
        data = {
            "borrowing": self.borrowing,
            "type": Payment.Type.PAYMENT,
            "session_url": "https://checkout.stripe.com/test",
            "session_id": "cs_test_123",
            "money_to_pay": Decimal("10.50"),
        }
        data.update(kwargs)

        return Payment.objects.create(**data)

    def test_payment_has_pending_status_by_default(self):
        payment = self.create_payment()

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
            payment.borrowing,
            self.borrowing,
        )

    def test_payment_amount_must_be_positive(self):
        payment = Payment(
            borrowing=self.borrowing,
            type=Payment.Type.PAYMENT,
            session_url="https://checkout.stripe.com/test",
            session_id="cs_test_invalid",
            money_to_pay=Decimal("0.00"),
        )

        with self.assertRaises(ValidationError):
            payment.full_clean()

    def test_stripe_session_id_must_be_unique(self):
        self.create_payment()

        duplicate = Payment(
            borrowing=self.borrowing,
            type=Payment.Type.FINE,
            session_url="https://checkout.stripe.com/test2",
            session_id="cs_test_123",
            money_to_pay=Decimal("5.00"),
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_cannot_delete_borrowing_with_payment(self):
        self.create_payment()

        with self.assertRaises(ProtectedError):
            self.borrowing.delete()

        self.assertTrue(
            Borrowing.objects.filter(
                pk=self.borrowing.pk
            ).exists()
        )
