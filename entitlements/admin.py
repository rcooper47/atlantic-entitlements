from django.contrib import admin

from .models import Entitlement, Feature, Product


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    filter_horizontal = ("features",)


@admin.register(Entitlement)
class EntitlementAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "product",
        "granted_at",
        "expires_at",
        "revoked_at",
    )
    list_filter = ("product",)
    search_fields = ("user__username",)
    readonly_fields = ("granted_at",)
    autocomplete_fields = ("user", "product")
