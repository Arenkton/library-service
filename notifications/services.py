from django.utils import timezone

from borrowings.models import Borrowing


def get_overdue_borrowings():
    today = timezone.localdate()

    return (
        Borrowing.objects.filter(
            expected_return_date__lte=today,
            actual_return_date__isnull=True,
        )
        .select_related("book", "user")
        .order_by("expected_return_date", "pk")
    )
