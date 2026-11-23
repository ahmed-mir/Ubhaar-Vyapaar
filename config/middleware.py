from django.conf import settings


class PermissionsPolicyMiddleware:
    """Add the application's restrictive browser feature policy."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault(
            "Permissions-Policy",
            settings.SECURE_PERMISSIONS_POLICY,
        )
        return response
