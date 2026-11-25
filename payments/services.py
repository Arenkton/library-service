from decimal import Decimal

from django.conf import settings
from stripe import StripeClient

from borrowings.models import Borrowing
from payments.models import Payment


def create_payment_for_borrowing(
    borrowing: Borrowing,
) -> Payment:
    existing_payment = Payment.objects.filter(
        borrowing=borrowing,
        type=Payment.Type.PAYMENT,
    ).first()

    if existing_payment is not None:
        return existing_payment
    days = (
        borrowing.expected_return_date
        - borrowing.borrow_date
    ).days

    if days <= 0:
        raise ValueError(
            "Borrowing duration must be positive."
        )

    money_to_pay = borrowing.book.daily_fee * days

    amount_cents = int(
        money_to_pay * Decimal("100")
    )

    client = StripeClient(settings.STRIPE_SECRET_KEY)

    session = client.v1.checkout.sessions.create({
        "mode": "payment",
        "line_items": [
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": amount_cents,
                    "product_data": {
                        "name": borrowing.book.title,
                    },
                },
                "quantity": 1,
            },
        ],
        "metadata": {
            "borrowing_id": str(borrowing.pk),
        },
        "success_url": settings.STRIPE_SUCCESS_URL,
        "cancel_url": settings.STRIPE_CANCEL_URL,
    })

    payment = Payment.objects.create(
        borrowing=borrowing,
        type=Payment.Type.PAYMENT,
        status=Payment.Status.PENDING,
        session_url=session.url,
        session_id=session.id,
        money_to_pay=money_to_pay,
    )

    return payment
