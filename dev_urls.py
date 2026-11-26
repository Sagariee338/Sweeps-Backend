from django.urls import path
from .dev_views import (
    WalletView,
    OrdersView,
    OrderView,
    SimulateView,
    ReconcileView,
    NotifyView,
)

urlpatterns = [
    path("wallet/", WalletView.as_view()),
    path("orders/", OrdersView.as_view()),
    path("orders/<uuid:order_id>/", OrderView.as_view()),
    path("orders/<uuid:order_id>/simulate/", SimulateView.as_view()),
    path("orders/<uuid:order_id>/reconcile/", ReconcileView.as_view()),
    path("notify/<str:kind>/", NotifyView.as_view()),
]
