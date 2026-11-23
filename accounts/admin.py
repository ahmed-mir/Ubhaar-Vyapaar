from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import PermissionDenied

from .auth_forms import RateLimitedAdminAuthenticationForm
from .models import User


# Keep the standard AdminSite login flow and staff checks, replacing only its
# form so failed Admin authentication uses the shared identifier limiter.
admin.site.login_form = RateLimitedAdminAuthenticationForm


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    actions = None

    fieldsets = UserAdmin.fieldsets + (
        ("Ubhaar-Vyapaar details", {
            "fields": ("role", "phone"),
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Ubhaar-Vyapaar details", {
            "fields": ("role", "phone"),
        }),
    )

    list_display = ("username", "email", "role", "is_staff")

    def has_delete_permission(self, request, obj=None):
        return False

    def delete_model(self, request, obj):
        raise PermissionDenied("Use the account privacy lifecycle to close accounts.")

    def delete_queryset(self, request, queryset):
        raise PermissionDenied("Use the account privacy lifecycle to close accounts.")
