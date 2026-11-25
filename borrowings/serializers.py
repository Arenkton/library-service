from django.db import transaction
from django.db.models import F
from django.utils import timezone

from rest_framework import serializers

from books.models import Book
from books.serializers import BookSerializer
from borrowings.models import Borrowing
from payments.serializers import PaymentSerializer


class BorrowingReadSerializer(serializers.ModelSerializer):
    book = BookSerializer(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    payments = PaymentSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Borrowing
        fields = (
            "id",
            "borrow_date",
            "expected_return_date",
            "actual_return_date",
            "book",
            "user",
            "is_active",
            "payments",
        )
        read_only_fields = fields


class BorrowingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Borrowing
        fields = (
            "id",
            "book",
            "borrow_date",
            "expected_return_date",
        )
        read_only_fields = ("id", "borrow_date")

    def validate_expected_return_date(self, value):
        if value <= timezone.localdate():
            raise serializers.ValidationError(
                "Expected return date must be in the future."
            )

        return value

    def create(self, validated_data):
        book = validated_data["book"]

        with transaction.atomic():
            updated = Book.objects.filter(
                pk=book.pk,
                inventory__gt=0,
            ).update(
                inventory=F("inventory") - 1
            )

            if updated == 0:
                raise serializers.ValidationError(
                    {"book": "No available copies of this book."}
                )

            borrowing = Borrowing.objects.create(
                **validated_data
            )

        return borrowing

    def to_representation(self, instance):
        return BorrowingReadSerializer(
            instance,
            context=self.context,
        ).data


class BorrowingFilterSerializer(serializers.Serializer):
    is_active = serializers.BooleanField(required=False)
    user_id = serializers.IntegerField(
        required=False,
        min_value=1,
    )
