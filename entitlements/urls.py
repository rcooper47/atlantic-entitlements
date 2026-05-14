from django.urls import path

from .views import EntitlementDetailView, UserEntitlementsView

app_name = "entitlements"

urlpatterns = [
    path(
        "users/<int:user_id>/entitlements/",
        UserEntitlementsView.as_view(),
        name="user-entitlements",
    ),
    path(
        "entitlements/<int:entitlement_id>/",
        EntitlementDetailView.as_view(),
        name="entitlement-detail",
    ),
]
