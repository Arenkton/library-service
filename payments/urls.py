from django.urls import include, path
from rest_framework.routers import DefaultRouter

from payments.views import (
    PaymentCancelView,
    PaymentSuccessView,
    PaymentViewSet,
)
from payments.webhooks import StripeWebhookView


router = DefaultRouter()
router.register("", PaymentViewSet, basename="payment")


urlpatterns = [
    path(
        "success/",
        PaymentSuccessView.as_view(),
        name="payment-success",
    ),
    path(
        "cancel/",
        PaymentCancelView.as_view(),
        name="payment-cancel",
    ),
    path(
        "webhook/",
        StripeWebhookView.as_view(),
        name="stripe-webhook",
    ),
    path("", include(router.urls)),
]
