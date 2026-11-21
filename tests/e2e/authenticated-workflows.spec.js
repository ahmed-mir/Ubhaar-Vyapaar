const { execFileSync } = require("node:child_process");
const { test, expect } = require("@playwright/test");
const { login, logout, uniqueRunId, dismissCookieBanner } = require("./helpers");

function runLocalDjango(code) {
  const python = process.platform === "win32" ? "venv/Scripts/python.exe" : "python";
  return execFileSync(
    python,
    ["manage.py", "shell", "--settings=config.settings_e2e", "-c", code],
    { cwd: process.cwd(), encoding: "utf8" }
  ).trim();
}

async function verifyResponsive(page, path, label) {
  await page.goto(path);
  await expect(page.locator("h1")).toHaveCount(1);
  for (const width of [320, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
      `${label} at ${width}px`
    ).toBeLessThanOrEqual(width);
  }
}

test.describe("authenticated Buyer and Manufacturer workflows", () => {
  test("local role fixtures show their orders, attention items, and permitted next actions", async ({ page }) => {
    test.skip(Boolean(process.env.UBHAAR_BASE_URL), "Workflow fixtures are created only in the local E2E database.");
    test.setTimeout(180000);

    const suffix = uniqueRunId().replace(/[^a-z0-9]/gi, "").slice(-12).toLowerCase();
    const prefix = `uv-p8-${suffix}`;
    const password = "LocalFixture@4821";
    const fixtureOutput = runLocalDjango(`
import json, uuid
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone
from marketplace.models import CapacityListing, ManufacturerProfile, QuoteRequest, Quotation, Order, Milestone, PaymentTransaction

User = get_user_model()
buyer = User.objects.create_user(username=${JSON.stringify(`${prefix}-buyer`)}, email=${JSON.stringify(`${prefix}-buyer@example.test`)}, password=${JSON.stringify(password)}, role="BUYER")
maker_user = User.objects.create_user(username=${JSON.stringify(`${prefix}-maker`)}, email=${JSON.stringify(`${prefix}-maker@example.test`)}, password=${JSON.stringify(password)}, role="MANUFACTURER")
maker = ManufacturerProfile.objects.create(user=maker_user, business_name=${JSON.stringify(`${prefix} Precision Works`)}, city="Pune", state="Maharashtra", is_verified=True)
listing = CapacityListing.objects.create(manufacturer=maker, title=${JSON.stringify(`${prefix} CNC capacity`)}, category=CapacityListing.Category.METAL, description="Local workflow fixture", price_per_unit=Decimal("125.00"), minimum_quantity=20, production_days=8, availability_status=CapacityListing.AvailabilityStatus.AVAILABLE, is_active=True)

incoming = QuoteRequest.objects.create(buyer=buyer, listing=listing, quantity=40, requirements="Anodized sample batch", delivery_location="Pune", status=QuoteRequest.Status.PENDING)
incoming_quote = Quotation.objects.create(quote_request=incoming, quantity=40, price_per_unit=Decimal("125.00"), production_days=8, status=Quotation.Status.SENT)

accepted = QuoteRequest.objects.create(buyer=buyer, listing=listing, quantity=25, requirements="Precision bracket run", delivery_location="Mumbai", status=QuoteRequest.Status.ACCEPTED)
accepted_quote = Quotation.objects.create(quote_request=accepted, quantity=25, price_per_unit=Decimal("130.00"), production_days=9, status=Quotation.Status.ACCEPTED)

direct_order = Order.objects.create(source=Order.Source.BUY_NOW, buyer=buyer, manufacturer=maker, listing=listing, specifications_snapshot={"delivery_location": "Pune", "requirements": "Fixed-price test order"}, quantity=20, agreed_unit_price=Decimal("125.00"), total_amount=Decimal("2500.00"), agreed_production_days=8, status=Order.Status.AWAITING_FUNDING, terms_locked_at=timezone.now())
Milestone.objects.create(order=direct_order, title="Production complete", percentage=80, amount=Decimal("2000.00"), status=Milestone.Status.PENDING, funding_status=Milestone.FundingStatus.NOT_FUNDED)
Milestone.objects.create(order=direct_order, title="Ready to ship", percentage=20, amount=Decimal("500.00"), status=Milestone.Status.PENDING, funding_status=Milestone.FundingStatus.NOT_FUNDED)

quotation_order = Order.objects.create(source=Order.Source.QUOTATION, quotation=accepted_quote, buyer=buyer, manufacturer=maker, listing=listing, specifications_snapshot={"delivery_location": "Mumbai", "requirements": accepted.requirements}, quantity=25, agreed_unit_price=Decimal("130.00"), total_amount=Decimal("3250.00"), agreed_production_days=9, status=Order.Status.IN_PRODUCTION, terms_locked_at=timezone.now())
Milestone.objects.create(order=quotation_order, title="Production complete", percentage=80, amount=Decimal("2600.00"), status=Milestone.Status.IN_PROGRESS, funding_status=Milestone.FundingStatus.FUNDED)
ready_to_ship = Milestone.objects.create(order=quotation_order, title="Ready to ship", percentage=20, amount=Decimal("650.00"), status=Milestone.Status.PENDING, funding_status=Milestone.FundingStatus.FUNDED)
PaymentTransaction.objects.create(buyer=buyer, milestone=ready_to_ship, amount=Decimal("650.00"), provider=PaymentTransaction.Provider.RAZORPAY, provider_order_id=${JSON.stringify("test_order_" + suffix)}, provider_payment_id=${JSON.stringify("test_payment_" + suffix)}, status=PaymentTransaction.Status.CAPTURED, captured_at=timezone.now())

from django.urls import reverse
print(json.dumps({"buyer": buyer.username, "maker": maker_user.username, "profile": reverse("edit_business_profile"), "buyer_orders": reverse("buyer_orders"), "buyer_requests": reverse("my_quote_requests"), "manufacturer_orders": reverse("manufacturer_orders"), "listing": listing.title, "direct_order": direct_order.pk, "quotation_order": quotation_order.pk, "direct_order_path": reverse("order_detail", args=[direct_order.pk]), "quotation_order_path": reverse("order_detail", args=[quotation_order.pk]), "incoming_quote": incoming_quote.pk}))
`);
    const fixture = JSON.parse(fixtureOutput.split(/\r?\n/).filter(Boolean).at(-1));

    try {
      await page.setViewportSize({ width: 390, height: 900 });
      await login(page, fixture.buyer, password);
      await page.goto("/buyer/dashboard/");
      await dismissCookieBanner(page);
      await expect(page.getByRole("heading", { level: 1, name: "Buyer dashboard" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Needs your attention" })).toBeVisible();
      await expect(page.getByRole("button", { name: /accept quotation and create order/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /pay milestone|fund milestone \(demo\)/i }).first()).toBeVisible();
      await expect(page.getByText("Order type: Buy Now").first()).toBeVisible();
      await expect(page.getByRole("button", { name: /start milestone/i })).toHaveCount(0);

      await page.goto(fixture.buyer_orders);
      await expect(page.getByText("Order type: Buy Now").first()).toBeVisible();
      await expect(page.getByText("Order type: Quotation").first()).toBeVisible();
      await verifyResponsive(page, fixture.buyer_orders, "Buyer orders");
      await verifyResponsive(page, fixture.buyer_requests, "Buyer quote requests");
      await page.goto(fixture.direct_order_path);
      await expect(page.getByText("Direct purchase", { exact: true })).toBeVisible();
      await expect(page.locator("#next-action-title")).toBeVisible();
      await verifyResponsive(page, fixture.direct_order_path, "Buyer order detail");

      await verifyResponsive(page, "/buyer/dashboard/", "Buyer dashboard");

      await logout(page);
      await login(page, fixture.maker, password);
      await page.goto("/manufacturer/dashboard/");
      await dismissCookieBanner(page);
      await expect(page.getByRole("heading", { level: 1, name: "Manufacturer dashboard" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Quote requests" })).toBeVisible();
      await expect(page.getByText("Order type: Quotation").first()).toBeVisible();
      await expect(page.getByText("Test payment recorded · Test Mode")).toBeVisible();
      await expect(page.getByRole("button", { name: /submit milestone .* for approval/i })).toBeVisible();
      await expect(page.getByRole("button", { name: /approve milestone/i })).toHaveCount(0);
      await expect(page.getByRole("link", { name: "Edit business profile" })).toHaveAttribute("href", fixture.profile);

      await page.goto(fixture.manufacturer_orders);
      await expect(page.getByText("Order type: Buy Now").first()).toBeVisible();
      await expect(page.getByText("Order type: Quotation").first()).toBeVisible();
      await verifyResponsive(page, fixture.manufacturer_orders, "Manufacturer orders");
      await verifyResponsive(page, fixture.profile, "Manufacturer profile edit");
      await page.goto(fixture.quotation_order_path);
      await expect(page.getByRole("button", { name: /submit for approval/i })).toBeVisible();
      await expect(page.getByRole("button", { name: /approve milestone/i })).toHaveCount(0);
      await verifyResponsive(page, fixture.quotation_order_path, "Manufacturer order detail");

      await verifyResponsive(page, "/manufacturer/dashboard/", "Manufacturer dashboard");
    } finally {
      runLocalDjango(`
from django.contrib.auth import get_user_model
from marketplace.models import Order, Quotation, QuoteRequest, CapacityListing, PaymentTransaction
User = get_user_model()
buyer = User.objects.filter(username=${JSON.stringify(fixture.buyer)}).first()
PaymentTransaction.objects.filter(milestone__order__buyer=buyer).delete()
Order.objects.filter(buyer=buyer).delete()
Quotation.objects.filter(quote_request__buyer=buyer).delete()
QuoteRequest.objects.filter(buyer=buyer).delete()
CapacityListing.objects.filter(title=${JSON.stringify(fixture.listing)}).delete()
User.objects.filter(username__in=${JSON.stringify([fixture.buyer, fixture.maker])}).delete()
`);
    }
  });
});
