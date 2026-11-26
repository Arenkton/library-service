from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from books.models import Book
from borrowings.models import Borrowing
from payments.models import Payment


User = get_user_model()


class FineConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="constraint-reader@example.com",
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

    def create_payment(
        self,
        borrowing,
        payment_type,
        session_id,
    ):
        return Payment.objects.create(
            borrowing=borrowing,
            type=payment_type,
            status=Payment.Status.PENDING,
            session_id=session_id,
            session_url=(
                f"https://checkout.stripe.com/{session_id}"
            ),
            money_to_pay=Decimal("9.00"),
        )

    def test_duplicate_fine_is_rejected(self):
        self.create_payment(
            self.borrowing,
            Payment.Type.FINE,
            "cs_test_fine_1",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.create_payment(
                    self.borrowing,
                    Payment.Type.FINE,
                    "cs_test_fine_2",
                )

        self.assertEqual(
            Payment.objects.filter(
                type=Payment.Type.FINE
            ).count(),
            1,
        )

    def test_regular_payment_and_fine_can_coexist(self):
        self.create_payment(
            self.borrowing,
            Payment.Type.PAYMENT,
            "cs_test_regular",
        )

        self.create_payment(
            self.borrowing,
            Payment.Type.FINE,
            "cs_test_fine",
        )

        self.assertEqual(
            self.borrowing.payments.count(),
            2,
        )

    def test_different_borrowings_can_have_fines(self):
        second_borrowing = Borrowing.objects.create(
            user=self.user,
            book=self.book,
            expected_return_date=(
                timezone.localdate() + timedelta(days=7)
            ),
        )

        self.create_payment(
            self.borrowing,
            Payment.Type.FINE,
            "cs_test_fine_1",
        )

        self.create_payment(
            second_borrowing,
            Payment.Type.FINE,
            "cs_test_fine_2",
        )

        self.assertEqual(
            Payment.objects.filter(
                type=Payment.Type.FINE
            ).count(),
            2,
        )
