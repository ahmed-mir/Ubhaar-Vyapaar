const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { test, expect } = require("@playwright/test");

function runLocalDjango(code) {
  const python = process.platform === "win32" ? "venv/Scripts/python.exe" : "python";
  return execFileSync(
    python,
    ["manage.py", "shell", "--settings=config.settings_e2e", "-c", code],
    { cwd: process.cwd(), encoding: "utf8" }
  ).trim();
}

test.describe("listing detail commercial experience", () => {
  test("commercial facts, valid CTAs, Manufacturer navigation, Sample restrictions, and responsive layout", async ({ page }) => {
    test.skip(Boolean(process.env.UBHAAR_BASE_URL), "Listing detail fixtures use the local E2E database.");

    const fixtureOutput = runLocalDjango(`
import json, uuid
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from marketplace.models import CapacityListing, ManufacturerProfile

User = get_user_model()
suffix = uuid.uuid4().hex[:10]
prefix = f"uv-detail-e2e-{suffix}"
maker_user = User.objects.create_user(
    username=f"{prefix}-maker", email=f"private-{suffix}@example.test",
    password="temporary-password", role="MANUFACTURER", phone="9876543210"
)
manufacturer = ManufacturerProfile.objects.create(
    user=maker_user,
    business_name=f"{prefix} Precision Manufacturing Cooperative",
    description="Precision machining and small-batch metal fabrication.",
    city="Leh", state="jammu and kashmir", pincode="194101", is_verified=True,
)
long_title = f"{prefix} CNC machined aluminium components for long-run industrial assemblies"
listing = CapacityListing.objects.create(
    manufacturer=manufacturer, title=long_title,
    category=CapacityListing.Category.METAL,
    description=("CNC machining for custom aluminium components. " * 4)
        + f"<script>window.detailXss_{suffix}=true</script>",
    machine_type="CNC milling", materials="Aluminium",
    technical_capabilities="Small batch runs with repeatable tolerances.",
    minimum_quantity=50, price_per_unit=Decimal("185.00"),
    batch_price=Decimal("9000.00"), production_days=8,
    available_capacity=1000, capacity_period="per month",
    availability_status=CapacityListing.AvailabilityStatus.AVAILABLE,
    is_active=True,
)
paused_listing = CapacityListing.objects.create(
    manufacturer=manufacturer, title=f"{prefix} paused capacity",
    category=CapacityListing.Category.METAL, description="Temporarily paused.",
    price_per_unit=Decimal("50.00"), minimum_quantity=10,
    production_days=5, availability_status=CapacityListing.AvailabilityStatus.PAUSED,
    is_active=True,
)
sample_user = User.objects.create_user(
    username=f"demo_mfr_{prefix}-sample", email=f"sample-{suffix}@example.test",
    password="temporary-password", role="MANUFACTURER"
)
sample = ManufacturerProfile.objects.create(
    user=sample_user, business_name=f"{prefix} Sample Works",
    description="Illustrative sample manufacturer.", city="Pune",
    state="Maharashtra", is_verified=False,
)
sample_listing = CapacityListing.objects.create(
    manufacturer=sample, title=f"{prefix} sample capacity",
    category=CapacityListing.Category.METAL, description="Illustrative sample capacity.",
    price_per_unit=Decimal("40.00"), minimum_quantity=20,
    production_days=6, availability_status=CapacityListing.AvailabilityStatus.AVAILABLE,
    is_active=True,
)
buyer = User.objects.create_user(
    username=f"{prefix}-buyer", email=f"buyer-{suffix}@example.test",
    password="temporary-password", role="BUYER"
)
print(json.dumps({
    "prefix": prefix,
    "buyerUsername": buyer.username,
    "buyerPassword": "temporary-password",
    "listingTitle": listing.title,
    "listingPath": reverse("listing_detail", args=[listing.pk]),
    "samplePath": reverse("listing_detail", args=[sample_listing.pk]),
    "pausedPath": reverse("listing_detail", args=[paused_listing.pk]),
    "manufacturerPath": reverse("manufacturer_profile", args=[manufacturer.pk]),
    "marketplacePath": reverse("marketplace"),
    "privateEmail": maker_user.email,
}))
`);
    const fixture = JSON.parse(fixtureOutput.split(/\r?\n/).filter(Boolean).at(-1));

    try {
      await page.setViewportSize({ width: 390, height: 900 });
      await page.goto("/accounts/login/");
      const rejectAnalytics = page.getByRole("button", { name: /reject analytics/i });
      if (await rejectAnalytics.isVisible()) await rejectAnalytics.click();
      await page.locator('[name="username"]').fill(fixture.buyerUsername);
      await page.locator('[name="password"]').fill(fixture.buyerPassword);
      await page.getByRole("button", { name: /^log in$/i }).click();
      await page.waitForURL((url) => !url.pathname.startsWith("/accounts/login/"));

      await page.goto(`${fixture.marketplacePath}?q=${encodeURIComponent(fixture.prefix)}`);
      await page.getByRole("link", { name: fixture.listingTitle }).click();
      await expect(page).toHaveURL(new RegExp(`${fixture.listingPath.replaceAll("/", "\\/")}$`));

      await expect(page.getByRole("heading", { level: 1, name: fixture.listingTitle })).toBeVisible();
      await expect(page.locator(".listing-sheet-heading .trust-badge")).toHaveText("Verified Manufacturer");
      await expect(page.locator(".detail-manufacturer-line")).toContainText("Leh, Jammu and Kashmir");
      await expect(page.locator(".detail-commercial-panel")).toContainText("185 / unit");
      await expect(page.locator(".detail-commercial-panel")).toContainText("50 units");
      await expect(page.locator(".detail-commercial-panel")).toContainText("8 days");
      await expect(page.locator(".detail-commercial-panel")).toContainText("1,000 units/month");
      await expect(page.locator(".detail-commercial-panel")).toContainText("Available");
      await expect(page.getByRole("link", { name: "Buy now" })).toBeVisible();
      await expect(page.getByRole("link", { name: "Request a quote" })).toBeVisible();
      await expect(page.getByText("Purchase at the displayed fixed price and terms.")).toBeVisible();
      await expect(page.locator(".description-content script")).toHaveCount(0);
      await expect(page.locator(".description-content")).toContainText("CNC machining for custom aluminium components.");
      await expect(page.locator(".listing-sheet-media .detail-image-placeholder")).toBeVisible();
      const bodyText = await page.locator("body").innerText();
      expect(bodyText).not.toContain(fixture.privateEmail);
      expect(bodyText).not.toContain("9876543210");
      expect(bodyText).not.toContain("194101");

      await page.getByRole("link", { name: "View Manufacturer profile" }).click();
      await expect(page).toHaveURL(new RegExp(`${fixture.manufacturerPath.replaceAll("/", "\\/")}$`));
      await expect(page.getByRole("heading", { level: 1 })).toContainText("Precision Manufacturing Cooperative");
      await page.goBack();
      await expect(page).toHaveURL(new RegExp(`${fixture.listingPath.replaceAll("/", "\\/")}$`));

      await page.goto(fixture.samplePath);
      await expect(page.getByText("Sample listing", { exact: true })).toBeVisible();
      await expect(page.getByText("Sample listing: quoting and purchasing are disabled.")).toBeVisible();
      await expect(page.getByRole("button", { name: "Save listing" })).toBeVisible();
      await expect(page.getByRole("link", { name: "Buy now" })).toHaveCount(0);
      await expect(page.getByRole("link", { name: "Request a quote" })).toHaveCount(0);

      await page.goto(fixture.pausedPath);
      await expect(page.getByText("This capacity is temporarily paused")).toBeVisible();
      await expect(page.getByRole("link", { name: "Buy now" })).toHaveCount(0);
      await expect(page.getByRole("link", { name: "Request a quote" })).toHaveCount(0);

      const screenshotDir = path.join("test-results", "phase4-listing-detail");
      fs.mkdirSync(screenshotDir, { recursive: true });
      for (const width of [320, 390, 768, 1024, 1440]) {
        await page.setViewportSize({ width, height: 900 });
        await page.goto(fixture.listingPath);
        await expect(page.locator("h1")).toHaveCount(1);
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth),
          `Listing detail should fit at ${width}px`
        ).toBeLessThanOrEqual(width);
        await expect(page.getByRole("link", { name: "Buy now" })).toBeVisible();
        await expect(page.getByRole("link", { name: "Request a quote" })).toBeVisible();
        const media = await page.locator(".listing-sheet-media").boundingBox();
        expect(media.width).toBeLessThanOrEqual(width);
        const placeholder = page.locator(".listing-sheet-media .detail-image-placeholder");
        if (await placeholder.isVisible()) {
          const placeholderBox = await placeholder.boundingBox();
          expect(Math.abs(placeholderBox.height - media.height)).toBeLessThanOrEqual(2);
        }
        await page.screenshot({ path: path.join(screenshotDir, `fixed-price-${width}.png`), fullPage: true });
      }
    } finally {
      runLocalDjango(`
from django.contrib.auth import get_user_model
User = get_user_model()
User.objects.filter(username__in=${JSON.stringify([
  `${fixture.prefix}-maker`,
  `demo_mfr_${fixture.prefix}-sample`,
  `${fixture.prefix}-buyer`,
])}).delete()
`);
    }
  });
});
