const { execFileSync } = require("node:child_process");
const { test, expect } = require("@playwright/test");

function runLocalDjango(code) {
  const python = process.platform === "win32" ? "venv/Scripts/python.exe" : "python";
  return execFileSync(
    python,
    ["manage.py", "shell", "--settings=config.settings_e2e", "-c", code],
    { cwd: process.cwd(), encoding: "utf8" }
  ).trim();
}

test.describe("public Manufacturer profile", () => {
  test("profile details, public listings, privacy, and responsive layout", async ({ page }) => {
    test.skip(Boolean(process.env.UBHAAR_BASE_URL), "Manufacturer profile fixtures use the local E2E database.");

    const fixtureOutput = runLocalDjango(`
import json, uuid
from decimal import Decimal
from django.contrib.auth import get_user_model
from marketplace.models import CapacityListing, ManufacturerProfile

User = get_user_model()
suffix = uuid.uuid4().hex[:10]
prefix = f"uv-profile-e2e-{suffix}"
user = User.objects.create_user(
    username=f"{prefix}-maker", email=f"private-{suffix}@example.test",
    password="temporary-password", role="MANUFACTURER", phone="9876543210"
)
manufacturer = ManufacturerProfile.objects.create(
    user=user,
    business_name=f"{prefix} Precision Manufacturing Cooperative",
    description=("Small-batch precision machining and fabrication capacity. " * 5)
        + f"<script>window.profileXss_{suffix}=true</script>",
    city="Leh", state="jammu and kashmir", pincode="194101", is_verified=True,
)
listing = CapacityListing.objects.create(
    manufacturer=manufacturer, title=f"{prefix} active CNC capacity",
    category=CapacityListing.Category.METAL, description="Public CNC machining capacity.",
    price_per_unit=Decimal("42.00"), minimum_quantity=25, production_days=12,
    availability_status=CapacityListing.AvailabilityStatus.AVAILABLE, is_active=True,
)
second_listing = CapacityListing.objects.create(
    manufacturer=manufacturer, title=f"{prefix} small fabrication capacity",
    category=CapacityListing.Category.METAL, description="Small fabrication capacity.",
    price_per_unit=Decimal("51.00"), minimum_quantity=15, production_days=9,
    availability_status=CapacityListing.AvailabilityStatus.LIMITED, is_active=True,
)
CapacityListing.objects.create(
    manufacturer=manufacturer, title=f"{prefix} inactive capacity",
    category=CapacityListing.Category.METAL, description="Not publicly available.",
    price_per_unit=Decimal("35.00"), is_active=False,
)
empty_user = User.objects.create_user(
    username=f"{prefix}-empty", email=f"empty-{suffix}@example.test",
    password="temporary-password", role="MANUFACTURER"
)
empty_manufacturer = ManufacturerProfile.objects.create(
    user=empty_user, business_name="Makers",
    description="", city="Puducherry", state="Puducherry", is_verified=True,
)
from django.urls import reverse
print(json.dumps({
    "prefix": prefix,
    "businessName": manufacturer.business_name,
    "listingTitle": listing.title,
    "secondListingTitle": second_listing.title,
    "profilePath": reverse("manufacturer_profile", args=[manufacturer.pk]),
    "emptyProfilePath": reverse("manufacturer_profile", args=[empty_manufacturer.pk]),
    "listingPath": reverse("listing_detail", args=[listing.pk]),
    "marketplacePath": reverse("marketplace"),
    "email": user.email,
}))
`);
    const fixture = JSON.parse(fixtureOutput.split(/\r?\n/).filter(Boolean).at(-1));

    try {
      await page.setViewportSize({ width: 390, height: 900 });
      await page.goto(`${fixture.marketplacePath}?q=${encodeURIComponent(fixture.prefix)}`);
      const listingLink = page.getByRole("link", { name: fixture.listingTitle });
      await expect(listingLink).toBeVisible();
      await listingLink.click();
      await expect(page).toHaveURL(new RegExp(`${fixture.listingPath.replaceAll("/", "\\/")}$`));
      await page.getByRole("link", { name: "View manufacturer profile" }).click();

      await expect(page.getByRole("heading", { level: 1, name: fixture.businessName })).toBeVisible();
      await expect(page.locator(".manufacturer-sheet-heading .record-meta")).toContainText("Leh, Jammu and Kashmir");
      await expect(page.getByText("Verified Manufacturer", { exact: true })).toBeVisible();
      await expect(page.getByText("Business profile verified by Ubhaar-Vyapaar.")).toBeVisible();
      await expect(page.getByRole("heading", { name: "About the company" })).toBeVisible();
      await expect(page.locator(".manufacturer-about-copy")).toContainText("Small-batch precision machining");
      await expect(page.locator(".manufacturer-about-copy script")).toHaveCount(0);
      await expect(page.locator(".manufacturer-about-copy")).toContainText(`<script>window.profileXss_${fixture.prefix.split("-").at(-1)}=true</script>`);
      await expect(page.getByRole("heading", { name: "Available manufacturing capacity" })).toBeVisible();
      await expect(page.locator(".manufacturer-listing-count")).toHaveText("2 active listings");
      await expect(page.getByRole("link", { name: fixture.listingTitle })).toBeVisible();
      await expect(page.getByRole("link", { name: fixture.secondListingTitle })).toBeVisible();
      await expect(page.getByText(new RegExp(`${fixture.prefix} inactive capacity`))).toHaveCount(0);
      await expect(page.getByRole("link", { name: "Edit business profile" })).toHaveCount(0);

      const renderedText = await page.locator("body").innerText();
      expect(renderedText).not.toContain(fixture.email);
      expect(renderedText).not.toContain("9876543210");
      expect(renderedText).not.toContain("194101");

      const profileListingPath = await page.getByRole("link", { name: fixture.listingTitle }).getAttribute("href");
      await page.goto(profileListingPath);
      await expect(page.getByRole("heading", { level: 1, name: fixture.listingTitle })).toBeVisible();

      for (const width of [320, 390, 768, 1024, 1440]) {
        await page.setViewportSize({ width, height: 900 });
        await page.goto(fixture.profilePath);
        await expect(page.locator("h1")).toHaveCount(1);
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth),
          `Manufacturer profile should fit at ${width}px`
        ).toBeLessThanOrEqual(width);
      }

      await page.setViewportSize({ width: 320, height: 900 });
      await page.goto(fixture.profilePath);
      await page.keyboard.press("Tab");
      await expect(page.locator(".skip-link")).toBeFocused();
      await page.goto(fixture.emptyProfilePath);
      await expect(page.getByRole("heading", { level: 1, name: "Makers" })).toBeVisible();
      await expect(page.getByText("No manufacturing capacity is currently listed.")).toBeVisible();
      await expect(page.getByRole("link", { name: "Browse marketplace" })).toHaveAttribute("href", fixture.marketplacePath);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
    } finally {
      runLocalDjango(`
from django.contrib.auth import get_user_model
User = get_user_model()
User.objects.filter(username__in=${JSON.stringify([`${fixture.prefix}-maker`, `${fixture.prefix}-empty`])}).delete()
`);
    }
  });
});
