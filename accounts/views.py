from django.contrib.auth import login
from django.shortcuts import redirect, render

from .forms import (
    BuyerRegistrationForm,
    ManufacturerRegistrationForm,
)
from django.contrib import messages
from django.db import transaction

from marketplace.models import ManufacturerProfile


def get_started(request):
    if request.user.is_authenticated:
        return redirect("home")
    return render(request, "accounts/get_started.html")


def register(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = BuyerRegistrationForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(
                request,
                "Your buyer account is ready. You can now browse capacity "
                "and request quotations from eligible listings.",
            )
            return redirect("home")
    else:
        form = BuyerRegistrationForm()

    return render(
        request,
        "accounts/register.html",
        {"form": form},
    )
def register_manufacturer(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = ManufacturerRegistrationForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                user = form.save()

                ManufacturerProfile.objects.create(
                    user=user,
                    business_name=form.cleaned_data["business_name"],
                    description=form.cleaned_data["description"],
                    city=form.cleaned_data["city"],
                    state=form.cleaned_data["state"],
                    is_verified=False,
                    kyc_status=ManufacturerProfile.KycStatus.UNDER_REVIEW,
                )

            login(request, user)

            messages.success(
                request,
                "Your manufacturer account is ready. "
                "Complete your business profile and manage your listings "
                "from the dashboard. Listings become public only after "
                "your business is verified.",
            )

            return redirect("manufacturer_dashboard")
    else:
        form = ManufacturerRegistrationForm()

    return render(
        request,
        "accounts/register_manufacturer.html",
        {"form": form},
    )
