from celery import shared_task

from borrowings.models import Borrowing
from notifications.telegram import (
    TelegramTemporaryError,
    send_telegram_message,
)
from notifications.services import get_overdue_borrowings


@shared_task(
    autoretry_for=(TelegramTemporaryError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def notify_new_borrowing(borrowing_id: int) -> bool:
    borrowing = (
        Borrowing.objects
        .select_related("book", "user")
        .filter(pk=borrowing_id)
        .first()
    )

    if borrowing is None:
        return False

    message = (
        "📚 New borrowing created!\n\n"
        f"Borrowing ID: {borrowing.pk}\n"
        f"Book: {borrowing.book.title}\n"
        f"User ID: {borrowing.user_id}\n"
        f"Borrow date: {borrowing.borrow_date}\n"
        f"Expected return: {borrowing.expected_return_date}"
    )

    return send_telegram_message(message)


@shared_task(
    autoretry_for=(TelegramTemporaryError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def notify_overdue_borrowings() -> int:
    overdue_borrowings = get_overdue_borrowings()
    notifications_sent = 0
    has_overdue = False

    for borrowing in overdue_borrowings:
        has_overdue = True

        message = (
            "⚠️ Overdue borrowing!\n\n"
            f"Borrowing ID: {borrowing.pk}\n"
            f"Book: {borrowing.book.title}\n"
            f"User ID: {borrowing.user_id}\n"
            f"Borrow date: {borrowing.borrow_date}\n"
            f"Expected return: {borrowing.expected_return_date}"
        )

        if send_telegram_message(message):
            notifications_sent += 1

    if not has_overdue:
        send_telegram_message(
            "No borrowings overdue today!"
        )

    return notifications_sent
