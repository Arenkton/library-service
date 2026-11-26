from decimal import Decimal

from django.test import SimpleTestCase

from payments.models import Payment
from payments.serializers import PaymentSerializer


class PaymentSerializerTests(SimpleTestCase):
    def setUp(self):
        self.payment = Payment(
            borrowing_id=42,
            status=Payment.Status.PENDING,
            type=Payment.Type.PAYMENT,
            session_url="https://checkout.stripe.com/test",
            session_id="cs_test_123",
            money_to_pay=Decimal("10.50"),
        )

    def test_serializes_payment(self):
        data = PaymentSerializer(self.payment).data

        self.assertEqual(data["status"], "PENDING")
        self.assertEqual(data["type"], "PAYMENT")
        self.assertEqual(data["borrowing"], 42)
        self.assertEqual(
            data["session_url"],
            "https://checkout.stripe.com/test",
        )
        self.assertEqual(
            data["session_id"],
            "cs_test_123",
        )
        self.assertEqual(
            data["money_to_pay"],
            "10.50",
        )

    def test_all_fields_are_read_only(self):
        serializer = PaymentSerializer()

        for field in serializer.fields.values():
            self.assertTrue(field.read_only)
