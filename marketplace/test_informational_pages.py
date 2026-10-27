from html.parser import HTMLParser

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse


PUBLIC_PAGES = (
    "how_it_works",
    "for_manufacturers",
    "about",
    "pricing_fees",
    "trust_safety",
    "faq",
    "contact",
    "grievance_redressal",
    "privacy_policy",
    "terms",
    "cookie_policy",
    "refund_policy",
)


class PageMetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.h1_count = 0
        self.title_text = []
        self.in_title = False
        self.meta = {}
        self.canonical = ""
        self.ids = set()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "h1":
            self.h1_count += 1
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            if attrs.get("name") in {"description", "twitter:title", "twitter:description"}:
                self.meta[attrs["name"]] = attrs.get("content", "")
            if attrs.get("property") in {"og:title", "og:description"}:
                self.meta[attrs["property"]] = attrs.get("content", "")
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href", "")
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "a" and attrs.get("href", "").startswith("#"):
            self.links.append(attrs["href"][1:])

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_text.append(data.strip())


class InformationalPageTests(TestCase):
    def parse(self, response):
        parser = PageMetadataParser()
        parser.feed(response.content.decode())
        return parser

    def test_public_pages_have_one_h1_unique_metadata_and_canonical(self):
        titles = set()
        descriptions = set()
        for route_name in PUBLIC_PAGES:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                parser = self.parse(response)
                title = "".join(parser.title_text).strip()
                description = parser.meta.get("description", "")
                self.assertEqual(parser.h1_count, 1)
                self.assertTrue(title)
                self.assertTrue(description)
                self.assertEqual(parser.meta.get("og:title"), title)
                self.assertEqual(parser.meta.get("twitter:title"), title)
                self.assertEqual(parser.meta.get("og:description"), description)
                self.assertEqual(parser.meta.get("twitter:description"), description)
                self.assertEqual(
                    parser.canonical,
                    f"{settings.SITE_ORIGIN}{reverse(route_name)}",
                )
                titles.add(title)
                descriptions.add(description)
                content = response.content.decode().lower()
                self.assertNotIn("todo", content)
                self.assertNotIn("not configured", content)
                self.assertTrue(all(anchor in parser.ids for anchor in parser.links))
        self.assertEqual(len(titles), len(PUBLIC_PAGES))
        self.assertEqual(len(descriptions), len(PUBLIC_PAGES))

    @override_settings(LEGAL_ENTITY_NAME="", LEGAL_CONTACT_EMAIL="")
    def test_missing_contact_values_disappear_cleanly(self):
        for route_name in (
            "contact",
            "grievance_redressal",
            "privacy_policy",
            "terms",
            "trust_safety",
        ):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "mailto:")
                self.assertNotContains(response, "LEGAL_CONTACT_EMAIL")
                self.assertNotContains(response, "LEGAL_ENTITY_NAME")
        trust = self.client.get(reverse("trust_safety"))
        self.assertContains(trust, reverse("contact"))
        self.assertNotContains(trust, "#communication-and-reporting")

    @override_settings(
        LEGAL_ENTITY_NAME="Ubhaar Trade Services",
        LEGAL_CONTACT_EMAIL="support@ubhaar-vyapaar.in",
        LEGAL_CONTACT_LABEL="Support email",
    )
    def test_real_configured_contact_details_render_on_applicable_pages(self):
        for route_name in ("contact", "privacy_policy", "terms", "trust_safety"):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertContains(response, "support@ubhaar-vyapaar.in")
                self.assertContains(response, "Ubhaar Trade Services")

    @override_settings(LEGAL_CONTACT_EMAIL="support@ubhaar-vyapaar.in")
    def test_general_support_contact_is_not_mislabeled_as_grievance_officer(self):
        response = self.client.get(reverse("grievance_redressal"))
        self.assertContains(response, "order messages")
        main_content = response.content.decode().split('<main', 1)[1].split('</main>', 1)[0]
        self.assertNotIn("support@ubhaar-vyapaar.in", main_content)
        self.assertNotContains(response, "Grievance officer:")

    @override_settings(
        GRIEVANCE_OFFICER_NAME="R. Sharma",
        GRIEVANCE_CONTACT_EMAIL="grievance@ubhaar-vyapaar.in",
    )
    def test_configured_grievance_details_appear(self):
        response = self.client.get(reverse("grievance_redressal"))
        self.assertContains(response, "R. Sharma")
        self.assertContains(response, "grievance@ubhaar-vyapaar.in")

    @override_settings(LEGAL_CONTACT_EMAIL="support@example.org")
    def test_placeholder_contact_email_is_not_presented_as_real_contact(self):
        response = self.client.get(reverse("contact"))
        self.assertNotContains(response, "support@example.org")
        self.assertNotContains(response, "mailto:")

    def test_faq_is_grouped_accessible_and_matches_current_behavior(self):
        response = self.client.get(reverse("faq"))
        for label in (
            "Marketplace",
            "Buyers",
            "Manufacturers",
            "Quotations",
            "Orders and milestones",
            "Verification",
            "Payments",
            "Accounts",
        ):
            self.assertContains(response, label)
        self.assertEqual(response.content.count(b"<details>"), 10)
        self.assertContains(response, "Sample listings are illustrative")
        self.assertContains(response, "funding or release labels")
        self.assertNotContains(response, "FAQPage")

    def test_pricing_trust_and_sample_language_stay_factual(self):
        pricing = self.client.get(reverse("pricing_fees"))
        self.assertContains(pricing, "does not calculate or collect platform fees")
        self.assertContains(pricing, "does not process real payments")
        self.assertContains(pricing, "money is collected, held, moved, or released")
        self.assertNotContains(pricing, "commission")
        self.assertNotContains(pricing, "subscription")
        self.assertNotContains(pricing, "escrow")
        self.assertNotContains(pricing, "Free during the pilot")

        trust = self.client.get(reverse("trust_safety"))
        self.assertContains(trust, "A KYC status by itself does not display the badge")
        self.assertContains(trust, "Sample manufacturers are not shown with the Verified badge")
        self.assertContains(trust, "not a certification")
        self.assertContains(trust, "insurance")
        self.assertContains(trust, "Report a concern")
        self.assertContains(trust, "No response time or dispute outcome is promised")
        self.assertNotContains(trust, "escrow")

        about = self.client.get(reverse("about"))
        self.assertContains(about, "A marketplace for manufacturing capacity")
        self.assertContains(about, "early-access pilot")
        self.assertContains(about, "Manufacturers publish capacity listings")
        self.assertContains(about, "Accepting a quotation creates an order")
        self.assertNotContains(about, "escrow")
        self.assertNotContains(about, "Our team")

    @override_settings(
        GRIEVANCE_OFFICER_NAME="R. Sharma",
        GRIEVANCE_CONTACT_EMAIL="grievance@ubhaar-vyapaar.in",
    )
    def test_configured_grievance_contact_is_shown_on_trust_page(self):
        response = self.client.get(reverse("trust_safety"))
        self.assertContains(response, "Grievance officer: R. Sharma")
        self.assertContains(response, "grievance@ubhaar-vyapaar.in")
        self.assertContains(response, reverse("grievance_redressal"))

    def test_manufacturer_page_omits_unconfigured_documents_and_review_time(self):
        response = self.client.get(reverse("for_manufacturers"))
        self.assertContains(response, reverse("register_manufacturer"))
        self.assertNotContains(response, "required documents")
        self.assertNotContains(response, "review time")
        self.assertNotContains(response, "success rate")

    @override_settings(
        MANUFACTURER_REQUIRED_DOCUMENTS=["Business registration record", "GST registration"],
        MANUFACTURER_REVIEW_TIME="Three business days",
    )
    def test_configured_manufacturer_documents_and_review_time_appear(self):
        response = self.client.get(reverse("for_manufacturers"))
        self.assertContains(response, "Business registration record")
        self.assertContains(response, "GST registration")
        self.assertContains(response, "Expected review time: Three business days")
