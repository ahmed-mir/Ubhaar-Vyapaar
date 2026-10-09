from django.contrib import admin

from .models import (
    ManufacturerProfile,
    CapacityListing,
    QuoteRequest,
    Quotation,
    SavedListing,
    Notification,
)


@admin.register(ManufacturerProfile)
class ManufacturerProfileAdmin(admin.ModelAdmin):
    list_display = (
        "business_name",
        "user",
        "city",
        "is_verified",
    )
    list_filter = ("is_verified", "state")
    search_fields = ("business_name", "city")


@admin.register(CapacityListing)
class CapacityListingAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "manufacturer",
        "category",
        "minimum_quantity",
        "price_per_unit",
        "production_days",
        "availability_status",
        "is_active",
    )
    list_filter = ("is_active", "availability_status", "category")
    search_fields = (
        "title",
        "manufacturer__business_name",
        "machine_type",
        "materials",
        "cluster",
    )


@admin.register(QuoteRequest)
class QuoteRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "buyer",
        "listing",
        "quantity",
        "status",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = (
        "buyer__username",
        "listing__title",
    )
    readonly_fields = ("created_at",)    

@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "quote_request",
        "price_per_unit",
        "quantity",
        "subtotal",
        "production_days",
        "status",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = (
        "quote_request__buyer__username",
        "quote_request__listing__title",
        "quote_request__listing__manufacturer__business_name",
    )
    readonly_fields = (
        "subtotal",
        "created_at",
        "responded_at",
    )
    list_select_related = (
        "quote_request",
        "quote_request__listing",
    )


@admin.register(SavedListing)
class SavedListingAdmin(admin.ModelAdmin):
    list_display = ("buyer", "listing", "created_at")
    search_fields = ("buyer__username", "listing__title")
    readonly_fields = ("created_at",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "destination", "is_read", "created_at")
    list_filter = ("destination", "is_read")
    search_fields = ("recipient__username", "message")
    readonly_fields = ("created_at",)
