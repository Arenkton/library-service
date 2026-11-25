from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"

    class Type(models.TextChoices):
        PAYMENT = "PAYMENT", "Payment"
        FINE = "FINE", "Fine"

    borrowing = models.ForeignKey(
        "borrowings.Borrowing",
        on_delete=models.PROTECT,
        related_name="payments",
    )

    status = models.CharField(
        max_length=7,
        choices=Status.choices,
        default=Status.PENDING,
    )

    type = models.CharField(
        max_length=7,
        choices=Type.choices,
    )

    session_url = models.URLField(max_length=2048)

    session_id = models.CharField(
        max_length=255,
        unique=True,
    )

    money_to_pay = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.01")),
        ],
    )

    def __str__(self):
        return (
            f"Payment #{self.pk} - "
            f"{self.type} - {self.status}"
        )
