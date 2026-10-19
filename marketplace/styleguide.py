from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render


@user_passes_test(lambda user: user.is_active and user.is_staff)
def styleguide(request):
    """Internal visual reference, available to active staff accounts only."""
    return render(request, "marketplace/styleguide.html")
