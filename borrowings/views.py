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
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from books.models import Book
from borrowings.models import Borrowing
from borrowings.serializers import (
    BorrowingCreateSerializer,
    BorrowingFilterSerializer,
    BorrowingReadSerializer,
)
import logging

from kombu.exceptions import OperationalError
from notifications.tasks import notify_new_borrowing


logger = logging.getLogger(__name__)


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
    queryset = Borrowing.objects.select_related(
        "book",
        "user",
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
        borrowing = serializer.save(user=self.request.user)

        def enqueue_notification():
            try:
                notify_new_borrowing.delay(borrowing.pk)
            except OperationalError:
                logger.exception(
                    "Failed to queue notification for borrowing %s",
                    borrowing.pk,
                )

        transaction.on_commit(enqueue_notification)

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

        with transaction.atomic():
            updated = Borrowing.objects.filter(
                pk=borrowing.pk,
                actual_return_date__isnull=True,
            ).update(
                actual_return_date=timezone.localdate()
            )

            if updated == 0:
                raise ValidationError(
                    {"detail": "This book has already been returned."}
                )

            Book.objects.filter(
                pk=borrowing.book_id
            ).update(
                inventory=F("inventory") + 1
            )

        borrowing.refresh_from_db()

        serializer = self.get_serializer(borrowing)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
