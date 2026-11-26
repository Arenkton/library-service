import logging

from celery import shared_task
from stripe import StripeError

from borrowings.models import Borrowing
from payments.services import create_fine_payment_for_borrowing

from django.db.models import F
from kombu.exceptions import OperationalError

from payments.models import Payment


logger = logging.getLogger(__name__)


@shared_task(
    autoretry_for=(StripeError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def create_fine_for_returned_borrowing(
    borrowing_id: int,
) -> bool:
    borrowing = (
        Borrowing.objects
        .select_related("book")
        .filter(pk=borrowing_id)
        .first()
    )

    if borrowing is None:
        return False

    if borrowing.actual_return_date is None:
        return False

    fine = create_fine_payment_for_borrowing(
        borrowing
    )

    return fine is not None


@shared_task
def enqueue_missing_fines() -> int:
    overdue_borrowings = (
        Borrowing.objects
        .filter(
            actual_return_date__gt=F("expected_return_date")
        )
        .exclude(
            payments__type=Payment.Type.FINE
        )
        .values_list("pk", flat=True)
    )

    queued_count = 0

    for borrowing_id in overdue_borrowings.iterator(
        chunk_size=100
    ):
        try:
            create_fine_for_returned_borrowing.delay(
                borrowing_id
            )
        except OperationalError:
            logger.exception(
                "Failed to queue fine for borrowing %s",
                borrowing_id,
            )
            break

        queued_count += 1

    return queued_count
