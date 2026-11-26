from django.db import transaction
from django.db.models import F
from django.utils import timezone

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
)
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from books.models import Book
from borrowings.models import Borrowing
from borrowings.serializers import (
    BorrowingCreateSerializer,
    BorrowingFilterSerializer,
    BorrowingReadSerializer,
)
from payments.services import create_payment_for_borrowing
from payments.tasks import create_fine_for_returned_borrowing
import logging

from kombu.exceptions import OperationalError
from notifications.tasks import notify_new_borrowing
from stripe import StripeError


logger = logging.getLogger(__name__)


class PaymentServiceUnavailable(APIException):
    status_code = 503
    default_detail = (
        "Payment service is temporarily unavailable. "
        "Please try again later."
    )
    default_code = "payment_service_unavailable"


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                name="is_active",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description=(
                    "Filter active (true) or returned "
                    "(false) borrowings."
                ),
            ),
            OpenApiParameter(
                name="user_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description=(
                    "Filter borrowings by user ID. "
                    "Only applies to admin users."
                ),
            ),
        ],
    ),
)
class BorrowingViewSet(
    mixins.CreateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = (
        Borrowing.objects
        .select_related("book", "user")
        .prefetch_related("payments")
    )
    serializer_class = BorrowingReadSerializer
    permission_classes = (IsAuthenticated,)

    def get_serializer_class(self):
        if self.action == "create":
            return BorrowingCreateSerializer

        return BorrowingReadSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        if not self.request.user.is_staff:
            queryset = queryset.filter(
                user=self.request.user
            )

        if self.action != "list":
            return queryset

        filter_serializer = BorrowingFilterSerializer(
            data=self.request.query_params.dict()
        )
        filter_serializer.is_valid(raise_exception=True)

        filters = filter_serializer.validated_data

        if "is_active" in filters:
            queryset = queryset.filter(
                actual_return_date__isnull=filters["is_active"]
            )

        if self.request.user.is_staff and "user_id" in filters:
            queryset = queryset.filter(
                user_id=filters["user_id"]
            )

        return queryset

    def perform_create(self, serializer):
        with transaction.atomic():
            borrowing = serializer.save(
                user=self.request.user
            )

            try:
                create_payment_for_borrowing(borrowing)
            except StripeError as exc:
                logger.exception(
                    "Failed to create Stripe payment "
                    "for borrowing %s",
                    borrowing.pk,
                )
                raise PaymentServiceUnavailable() from exc

            def enqueue_notification():
                try:
                    notify_new_borrowing.delay(
                        borrowing.pk
                    )
                except OperationalError:
                    logger.exception(
                        "Failed to queue notification "
                        "for borrowing %s",
                        borrowing.pk,
                    )

            transaction.on_commit(
                enqueue_notification
            )

    @extend_schema(
        request=None,
        responses={200: BorrowingReadSerializer},
        description=(
            "Return an active borrowing and increase "
            "the book inventory by one."
        ),
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="return",
    )
    def return_book(self, request, pk=None):
        borrowing = self.get_object()
        returned_on = timezone.localdate()

        with transaction.atomic():
            updated = Borrowing.objects.filter(
                pk=borrowing.pk,
                actual_return_date__isnull=True,
            ).update(
                actual_return_date=returned_on
            )

            if updated == 0:
                raise ValidationError({
                    "detail": "This book has already been returned."
                })

            Book.objects.filter(
                pk=borrowing.book_id
            ).update(
                inventory=F("inventory") + 1
            )

            if returned_on > borrowing.expected_return_date:
                def enqueue_fine():
                    try:
                        create_fine_for_returned_borrowing.delay(
                            borrowing.pk
                        )
                    except OperationalError:
                        logger.exception(
                            "Failed to queue fine for borrowing %s",
                            borrowing.pk,
                        )

                transaction.on_commit(enqueue_fine)

        borrowing.refresh_from_db()

        serializer = self.get_serializer(borrowing)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
