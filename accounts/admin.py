from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
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