from decimal import Decimal

from django.conf import settings
from django.shortcuts import get_object_or_404

from stripe import StripeClient, StripeError

from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from payments.models import Payment
from payments.serializers import PaymentSerializer


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = (IsAuthenticated,)

    queryset = Payment.objects.select_related(
        "borrowing",
        "borrowing__user",
        "borrowing__book",
    ).order_by("-id")

    def get_queryset(self):
        queryset = super().get_queryset()

        if not self.request.user.is_staff:
            queryset = queryset.filter(
                borrowing__user=self.request.user
            )

        return queryset


class StripeServiceUnavailable(APIException):
    status_code = 503
    default_detail = "Stripe is temporarily unavailable."
    default_code = "stripe_unavailable"


class PaymentSuccessView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        session_id = request.query_params.get(
            "session_id"
        )

        if not session_id:
            raise ValidationError({
                "session_id": "This parameter is required."
            })

        payment = get_object_or_404(
            Payment,
            session_id=session_id,
        )

        try:
            client = StripeClient(
                settings.STRIPE_SECRET_KEY
            )
            session = (
                client.v1.checkout.sessions.retrieve(
                    session_id
                )
            )
        except StripeError as exc:
            raise StripeServiceUnavailable() from exc

        expected_amount = int(
            payment.money_to_pay * Decimal("100")
        )

        metadata = session.metadata or {}

        if (
            session.id != payment.session_id
            or session.currency != "usd"
            or session.amount_total != expected_amount
            or metadata.get("borrowing_id")
            != str(payment.borrowing_id)
        ):
            raise ValidationError(
                "Stripe session details do not match."
            )

        if (
            session.status != "complete"
            or session.payment_status != "paid"
        ):
            return Response({
                "message": "Payment is not completed yet.",
                "status": payment.status,
            })

        Payment.objects.filter(
            pk=payment.pk,
            status=Payment.Status.PENDING,
        ).update(
            status=Payment.Status.PAID
        )

        return Response({
            "message": "Payment confirmed successfully.",
            "status": Payment.Status.PAID,
        })


class PaymentCancelView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response({
            "message": (
                "Checkout was canceled. "
                "You can try the payment link again "
                "while the session is still active."
            ),
        })
