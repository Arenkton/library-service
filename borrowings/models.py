from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Borrowing(models.Model):
    borrow_date = models.DateField(
        default=timezone.localdate,
        editable=False,
    )
    expected_return_date = models.DateField()
    actual_return_date = models.DateField(
        null=True,
        blank=True,
    )
    book = models.ForeignKey(
        "books.Book",
        on_delete=models.CASCADE,
        related_name="borrowings",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="borrowings",
    )

    class Meta:
        ordering = ("-borrow_date", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    expected_return_date__gt=F("borrow_date")
                ),
                name="borrowing_expected_after_borrow",
            ),
            models.CheckConstraint(
                condition=(
                    Q(actual_return_date__isnull=True)
                    | Q(actual_return_date__gte=F("borrow_date"))
                ),
                name="borrowing_actual_not_before_borrow",
            ),
        ]

    @property
    def is_active(self):
        return self.actual_return_date is None

    def __str__(self):
        return f"Borrowing #{self.pk}: {self.book.title}"
