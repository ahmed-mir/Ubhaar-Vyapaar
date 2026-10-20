from django.contrib import admin

from .models import (
    ManufacturerProfile,
    CapacityListing,
    ContactSubmission,
    Order,
    Milestone,
    OrderMessage,
    QuoteRequest,
    Quotation,
    Review,
    SavedListing,
    Notification,
)


@admin.register(ContactSubmission)
class ContactSubmissionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "name", "email", "role", "is_handled")
    list_display_links = ("created_at", "name")
    list_editable = ("is_handled",)
    list_filter = ("role", "is_handled", "created_at")
    search_fields = ("name", "email", "message")
    readonly_fields = ("name", "email", "role", "message", "created_at")
    date_hierarchy = "created_at"
    ordering = ("-created_at", "-pk")


@admin.register(ManufacturerProfile)
class ManufacturerProfileAdmin(admin.ModelAdmin):
    list_display = (
        "business_name",
        "user",
        "city",
        "is_verified",
        "kyc_status",
    )
    list_filter = ("is_verified", "kyc_status", "state")
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


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "buyer",
        "manufacturer",
        "listing",
        "status",
        "total_amount",
        "terms_locked_at",
    )
    list_filter = ("status", "terms_locked_at")
    search_fields = (
        "buyer__username",
        "manufacturer__business_name",
        "listing__title",
    )
    readonly_fields = (
        "terms_locked_at",
        "created_at",
        "updated_at",
    )


@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "title",
        "status",
        "percentage",
        "amount",
    )
    list_filter = ("status",)
    search_fields = ("title", "order__listing__title")
    readonly_fields = ("completed_at", "approved_at", "created_at", "updated_at")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "buyer",
        "manufacturer",
        "overall_rating",
        "created_at",
    )
    list_filter = ("overall_rating", "created_at")
    search_fields = (
        "buyer__username",
        "manufacturer__business_name",
        "comment",
    )
    readonly_fields = ("created_at",)


@admin.register(OrderMessage)
class OrderMessageAdmin(admin.ModelAdmin):
    list_display = ("order", "sender", "created_at")
    search_fields = ("order__listing__title", "sender__username", "body")
    readonly_fields = ("created_at",)
    list_select_related = ("order", "sender")


@admin.register(SavedListing)
class SavedListingAdmin(admin.ModelAdmin):
    list_display = ("buyer", "listing", "created_at")
    search_fields = ("buyer__username", "listing__title")
    readonly_fields = ("created_at",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "destination", "order", "is_read", "created_at")
    list_filter = ("destination", "is_read")
    search_fields = ("recipient__username", "message", "order__listing__title")
    readonly_fields = ("created_at",)
    list_select_related = ("recipient", "order")
