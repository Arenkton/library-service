import logging
from decimal import Decimal

import stripe

from django.conf import settings

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import Payment


logger = logging.getLogger(__name__)


class StripeWebhookView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        webhook_secret = settings.STRIPE_WEBHOOK_SECRET

        if not webhook_secret:
            logger.error("Stripe webhook secret is not configured.")
            return Response(
                {"detail": "Webhook is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        signature = request.headers.get("Stripe-Signature")

        if not signature:
            return Response(
                {"detail": "Missing Stripe signature."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            event = stripe.Webhook.construct_event(
                request.body,
                signature,
                webhook_secret,
            )
        except (
            ValueError,
            stripe.error.SignatureVerificationError,
        ):
            return Response(
                {"detail": "Invalid Stripe webhook."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if event["type"] not in (
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
        ):
            return Response({"status": "ignored"})

        session = event["data"]["object"].to_dict()

        if (
            session.get("status") != "complete"
            or session.get("payment_status") != "paid"
        ):
            return Response({"status": "not_paid"})

        payment = Payment.objects.filter(
            session_id=session.get("id"),
        ).first()

        if payment is None:
            logger.warning(
                "No payment found for Stripe session %s",
                session.get("id"),
            )
            return Response({"status": "ignored"})

        expected_amount = int(
            payment.money_to_pay * Decimal("100")
        )

        metadata = session.get("metadata") or {}

        if (
            session.get("currency") != "usd"
            or session.get("amount_total") != expected_amount
            or metadata.get("borrowing_id")
            != str(payment.borrowing_id)
        ):
            logger.error(
                "Stripe session data mismatch for payment %s",
                payment.pk,
            )
            return Response(
                {"detail": "Payment details mismatch."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated = Payment.objects.filter(
            pk=payment.pk,
            status=Payment.Status.PENDING,
        ).update(
            status=Payment.Status.PAID,
        )

        if updated:
            logger.info(
                "Payment %s confirmed by Stripe webhook.",
                payment.pk,
            )

        return Response({"status": "success"})
