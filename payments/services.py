from decimal import Decimal

from django.conf import settings
from django.db import transaction
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


def create_fine_payment_for_borrowing(
    borrowing: Borrowing,
) -> Payment | None:
    with transaction.atomic():
        locked_borrowing = (
            Borrowing.objects
            .select_for_update()
            .get(pk=borrowing.pk)
        )

        if locked_borrowing.actual_return_date is None:
            raise ValueError(
                "Borrowing must be returned before calculating a fine."
            )

        overdue_days = (
            locked_borrowing.actual_return_date
            - locked_borrowing.expected_return_date
        ).days

        if overdue_days <= 0:
            return None

        existing_payment = Payment.objects.filter(
            borrowing=locked_borrowing,
            type=Payment.Type.FINE,
        ).first()

        if existing_payment is not None:
            return existing_payment

        money_to_pay = (
            locked_borrowing.book.daily_fee
            * overdue_days
            * settings.FINE_MULTIPLIER
        ).quantize(Decimal("0.01"))

        if money_to_pay <= 0:
            raise ValueError(
                "Fine amount must be positive."
            )

        amount_cents = int(
            money_to_pay * Decimal("100")
        )

        client = StripeClient(
            settings.STRIPE_SECRET_KEY
        )

        session = client.v1.checkout.sessions.create(
            {
                "mode": "payment",
                "line_items": [
                    {
                        "price_data": {
                            "currency": "usd",
                            "unit_amount": amount_cents,
                            "product_data": {
                                "name": (
                                    "Overdue fine: "
                                    f"{locked_borrowing.book.title}"
                                ),
                            },
                        },
                        "quantity": 1,
                    },
                ],
                "metadata": {
                    "borrowing_id": str(locked_borrowing.pk),
                    "payment_type": Payment.Type.FINE,
                },
                "success_url": settings.STRIPE_SUCCESS_URL,
                "cancel_url": settings.STRIPE_CANCEL_URL,
            },
            options={
                "idempotency_key": (
                    f"library-service-fine-{locked_borrowing.pk}-v1"
                ),
            },
        )

        return Payment.objects.create(
            borrowing=locked_borrowing,
            type=Payment.Type.FINE,
            status=Payment.Status.PENDING,
            session_url=session.url,
            session_id=session.id,
            money_to_pay=money_to_pay,
        )
