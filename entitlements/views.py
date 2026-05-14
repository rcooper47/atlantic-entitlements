import json

from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .models import Entitlement, Product


def _serialize_entitlement(e):
    return {
        "id": e.id,
        "user_id": e.user_id,
        "product_name": e.product.name,
        "granted_at": e.granted_at.isoformat(),
        "expires_at": e.expires_at.isoformat() if e.expires_at else None,
        "revoked_at": e.revoked_at.isoformat() if e.revoked_at else None,
    }


def _error(message, status):
    return JsonResponse({"error": message}, status=status)


def _require_auth(request):
    if not request.user.is_authenticated:
        return _error("authentication required", 401)
    return None


def _require_staff(request):
    if not request.user.is_authenticated:
        return _error("authentication required", 401)
    if not request.user.is_staff:
        return _error("staff privileges required", 403)
    return None


def _parse_expires_at(raw):
    if raw is None:
        return None, None
    if not isinstance(raw, str):
        return None, "expires_at must be a string"
    dt = parse_datetime(raw)
    if dt is None:
        return None, "expires_at is not a valid ISO 8601 datetime"
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt, None


@method_decorator(csrf_exempt, name="dispatch")
class UserEntitlementsView(View):
    def get(self, request, user_id):
        denied = _require_auth(request)
        if denied:
            return denied

        User = get_user_model()
        if not User.objects.filter(pk=user_id).exists():
            return _error("user not found", 404)

        active_only = request.GET.get("active") == "true"
        qs = Entitlement.objects.filter(user_id=user_id).select_related("product")

        if active_only:
            active_qs = qs.active_for(user_id)
            payload = {
                "entitlements": [_serialize_entitlement(e) for e in active_qs],
                "features": sorted(Entitlement.objects.features_for(user_id)),
            }
        else:
            payload = {"entitlements": [_serialize_entitlement(e) for e in qs]}

        return JsonResponse(payload)

    def post(self, request, user_id):
        denied = _require_staff(request)
        if denied:
            return denied

        User = get_user_model()
        if not User.objects.filter(pk=user_id).exists():
            return _error("user not found", 404)

        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return _error("invalid JSON body", 400)

        product_name = body.get("product_name")
        if not product_name or not isinstance(product_name, str):
            return _error("product_name is required", 400)

        try:
            product = Product.objects.get(name=product_name)
        except Product.DoesNotExist:
            return _error(f"unknown product '{product_name}'", 404)

        expires_at, err = _parse_expires_at(body.get("expires_at"))
        if err:
            return _error(err, 400)

        entitlement = Entitlement.objects.create(
            user_id=user_id,
            product=product,
            expires_at=expires_at,
        )
        return JsonResponse(_serialize_entitlement(entitlement), status=201)


@method_decorator(csrf_exempt, name="dispatch")
class EntitlementDetailView(View):
    def delete(self, request, entitlement_id):
        denied = _require_staff(request)
        if denied:
            return denied

        try:
            entitlement = Entitlement.objects.get(pk=entitlement_id)
        except Entitlement.DoesNotExist:
            return _error("entitlement not found", 404)
        entitlement.revoke()
        return HttpResponse(status=204)
