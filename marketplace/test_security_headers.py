from decimal import Decimal
import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import path, reverse

from config.urls import urlpatterns as project_urlpatterns

from .models import CapacityListing, ManufacturerProfile


def _phase_5_test_server_error(request):
    raise RuntimeError("test-only server error")


urlpatterns = [
    *project_urlpatterns,
    path("phase-5-test-server-error/", _phase_5_test_server_error),
]


@override_settings(
    SECURE_CONTENT_TYPE_NOSNIFF=True,
    SECURE_REFERRER_POLICY="same-origin",
    X_FRAME_OPTIONS="DENY",
)
class BrowserSecurityHeaderTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="header-maker",
            password="not-a-real-password",
            role="MANUFACTURER",
        )
        manufacturer = ManufacturerProfile.objects.create(
            user=user,
            business_name="Header Works",
            city="Pune",
            state="Maharashtra",
            is_verified=True,
        )
        self.listing = CapacityListing.objects.create(
            manufacturer=manufacturer,
            title="Header test capacity",
            category=CapacityListing.Category.METAL,
            description="A public listing for header tests.",
            price_per_unit=Decimal("10.00"),
            minimum_quantity=1,
            production_days=3,
        )

    def assert_browser_headers(self, response):
        csp = response.headers["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("base-uri 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("script-src-attr 'none'", csp)
        self.assertNotIn("'unsafe-inline'", csp)
        self.assertNotIn("'unsafe-eval'", csp)
        self.assertNotRegex(csp, r"(?:^|\s)\*(?:\s|;|$)")
        self.assertEqual(
            response.headers["Permissions-Policy"],
            "camera=(), microphone=(), geolocation=(), usb=(), bluetooth=()",
        )
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Referrer-Policy"], "same-origin")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        nonce = re.search(r"'nonce-([^']+)'", csp)
        self.assertIsNotNone(nonce)
        self.assertIn(f'nonce="{nonce.group(1)}"', response.content.decode())
        return csp

    def test_public_and_auth_pages_receive_nonce_csp_and_security_headers(self):
        urls = (
            reverse("home"),
            reverse("marketplace"),
            reverse("login"),
            reverse("listing_detail", args=[self.listing.pk]),
        )
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assert_browser_headers(response)

    def test_policy_allows_only_required_third_party_origins(self):
        response = self.client.get(reverse("home"))
        csp = self.assert_browser_headers(response)
        self.assertIn("https://res.cloudinary.com", csp)
        self.assertIn("https://checkout.razorpay.com", csp)
        self.assertIn("https://api.razorpay.com", csp)
        self.assertIn("https://www.googletagmanager.com", csp)
        self.assertIn("https://www.google-analytics.com", csp)
        self.assertSetEqual(
            set(re.findall(r"https://[^\s;]+", csp)),
            {
                "https://res.cloudinary.com",
                "https://checkout.razorpay.com",
                "https://api.razorpay.com",
                "https://www.googletagmanager.com",
                "https://www.google-analytics.com",
                "https://region1.google-analytics.com",
            },
        )

    def test_404_response_has_security_headers(self):
        response = self.client.get("/phase-5-missing-page/")
        self.assertEqual(response.status_code, 404)
        self.assert_browser_headers(response)

    @override_settings(ROOT_URLCONF=__name__, DEBUG=False)
    def test_500_response_has_security_headers(self):
        self.client.raise_request_exception = False
        response = self.client.get("/phase-5-test-server-error/")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Content-Security-Policy", response.headers)
        self.assertIn("Permissions-Policy", response.headers)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")

    @override_settings(
        SECURE_SSL_REDIRECT=False,
        SECURE_HSTS_SECONDS=31_536_000,
        SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
        SECURE_HSTS_PRELOAD=True,
    )
    def test_hsts_is_sent_only_for_secure_requests(self):
        insecure = self.client.get(reverse("home"))
        secure = self.client.get(reverse("home"), secure=True)
        self.assertNotIn("Strict-Transport-Security", insecure.headers)
        self.assertEqual(
            secure.headers["Strict-Transport-Security"],
            "max-age=31536000; includeSubDomains; preload",
        )

    def test_admin_templates_render_with_nonce_csp(self):
        user = get_user_model().objects.create_superuser(
            username="header-admin",
            email="header-admin@example.invalid",
            password="not-a-real-password",
        )
        self.client.force_login(user)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        csp = self.assert_browser_headers(response)
        self.assertIn("script-src 'self' 'nonce-", csp)
