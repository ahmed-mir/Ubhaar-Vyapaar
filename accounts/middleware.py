"""HTTP response handling for login identifier throttle decisions."""


class LoginIdentifierThrottleResponseMiddleware:
    """Return 429 for public and Admin login attempts blocked by the limiter."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        decision = getattr(request, "_auth_login_identifier_throttled", None)
        if decision is not None and decision.throttled:
            response.status_code = 429
            response["Retry-After"] = str(decision.retry_after_seconds)
        return response
