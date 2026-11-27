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

test.describe("public marketplace filtering", () => {
  test("filter chips, sort, and clear preserve the appropriate GET state", async ({ page }) => {
    test.skip(Boolean(process.env.UBHAAR_BASE_URL), "Marketplace fixtures are limited to the local E2E database.");

    const fixtureOutput = runLocalDjango(`
import json, uuid
from decimal import Decimal
from django.contrib.auth import get_user_model
from marketplace.models import CapacityListing, ManufacturerProfile

User = get_user_model()
suffix = uuid.uuid4().hex[:12]
prefix = f"uv-filter-e2e-{suffix}"
verified_user = User.objects.create_user(
    username=f"{prefix}-verified", email=f"{prefix}-verified@example.com", role="MANUFACTURER"
)
verified = ManufacturerProfile.objects.create(
    user=verified_user, business_name=f"Verified filter {suffix}", city=f"FilterCity{suffix}",
    state="maharashtra", is_verified=True
)
sample_user = User.objects.create_user(
    username=f"demo_mfr_{prefix}-sample", email=f"{prefix}-sample@example.com", role="MANUFACTURER"
)
sample = ManufacturerProfile.objects.create(
    user=sample_user, business_name=f"Sample filter {suffix}", city=f"FilterCity{suffix}",
    state="Maharashtra", is_verified=False
)

def make_listing(manufacturer, title, moq, price, category=CapacityListing.Category.METAL):
    return CapacityListing.objects.create(
        manufacturer=manufacturer, title=title, description=f"Unique filter token {suffix}",
        category=category, minimum_quantity=moq,
        price_per_unit=Decimal(price), production_days=5,
        availability_status=CapacityListing.AvailabilityStatus.AVAILABLE, is_active=True
    )

eligible = make_listing(verified, f"Eligible filter {suffix}", 250, "20.00")
sample_listing = make_listing(sample, f"Sample filter {suffix}", 260, "10.00")
above_moq = make_listing(verified, f"Above MOQ filter {suffix}", 500, "15.00")
packaging = make_listing(
    verified, f"Packaging category filter {suffix}", 250, "18.00",
    category=CapacityListing.Category.PACKAGING
)
print(json.dumps({
    "suffix": suffix, "verified_username": verified_user.username,
    "sample_username": sample_user.username, "eligible": eligible.title,
    "sample": sample_listing.title, "above_moq": above_moq.title,
    "packaging": packaging.title
}))
`);
    const fixture = JSON.parse(fixtureOutput.split(/\r?\n/).filter(Boolean).at(-1));

    try {
      await page.setViewportSize({ width: 320, height: 900 });
      await page.goto("/marketplace/");

      const filterPanel = page.locator(".marketplace-filter-disclosure");
      await expect(filterPanel).toHaveJSProperty("open", false);
      await filterPanel.locator("summary").click();
      await expect(page.getByLabel("Category")).toBeVisible();

      await page.getByLabel("Search capacity").fill(fixture.suffix);
      await page.getByLabel("Location").fill("maharashtra");
      await page.getByRole("button", { name: "Search" }).click();
      await expect(page.locator(".marketplace-filter-chips")).toContainText("Location: Maharashtra");

      await filterPanel.locator("summary").click();
      await page.getByLabel("Category").selectOption("METAL");
      await page.getByLabel("Manufacturer verification").selectOption("verified");
      await page.getByLabel("MOQ up to (units)").fill("275");
      await page.getByRole("button", { name: "Apply filters" }).click();

      const results = page.locator(".marketplace-listing-rows");
      await expect(results).toContainText(fixture.eligible);
      await expect(results).not.toContainText(fixture.sample);
      await expect(results).not.toContainText(fixture.above_moq);
      await expect(page.locator("summary").filter({ hasText: "Filters (5)" })).toBeVisible();
      const categoryNav = page.getByRole("navigation", { name: "Browse manufacturing categories" });
      await expect(categoryNav.getByRole("link", { name: "Metal & Fabrication" })).toHaveAttribute("aria-current", "page");
      const packagingHref = await categoryNav.getByRole("link", { name: "Packaging", exact: true }).getAttribute("href");
      const packagingUrl = new URL(packagingHref, page.url());
      expect(packagingUrl.searchParams.get("q")).toBe(fixture.suffix);
      expect(packagingUrl.searchParams.get("category")).toBe("PACKAGING");
      expect(packagingUrl.searchParams.get("location")).toBe("maharashtra");
      expect(packagingUrl.searchParams.get("moq")).toBe("275");
      expect(packagingUrl.searchParams.get("verification")).toBe("verified");
      expect(packagingUrl.searchParams.has("page")).toBe(false);

      await page.getByRole("link", { name: "Remove Verified only filter" }).click();
      await expect(results).toContainText(fixture.eligible);
      await expect(results).toContainText(fixture.sample);
      await expect(results).not.toContainText(fixture.above_moq);
      await expect(page.locator(".marketplace-filter-chips")).toContainText("Location: Maharashtra");
      await expect(page.locator(".marketplace-filter-chips")).toContainText("MOQ ≤ 275");
      const allCategoriesHref = await categoryNav.getByRole("link", { name: "All categories" }).getAttribute("href");
      const allCategoriesUrl = new URL(allCategoriesHref, page.url());
      expect(allCategoriesUrl.searchParams.get("q")).toBe(fixture.suffix);
      expect(allCategoriesUrl.searchParams.get("location")).toBe("maharashtra");
      expect(allCategoriesUrl.searchParams.get("moq")).toBe("275");
      expect(allCategoriesUrl.searchParams.has("category")).toBe(false);

      await page.getByLabel("Sort").selectOption("price");
      await page.getByRole("button", { name: "Search" }).click();
      await expect(page).toHaveURL(/location=maharashtra/);
      await expect(page).toHaveURL(/moq=275/);
      await expect(page).toHaveURL(/sort=price/);
      await expect(page.locator(".marketplace-filter-chips")).toContainText("Location: Maharashtra");

      await page.getByRole("link", { name: "Clear all" }).click();
      await expect(page).toHaveURL("/marketplace/?sort=price");
      await expect(page.locator(".marketplace-filter-chips")).toHaveCount(0);
      await expect(page.getByLabel("Sort")).toHaveValue("price");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
    } finally {
      runLocalDjango(`
from django.contrib.auth import get_user_model
User = get_user_model()
User.objects.filter(username__in=${JSON.stringify([fixture.verified_username, fixture.sample_username])}).delete()
`);
    }
  });

  test("zero results explain recovery actions and long State chips fit mobile", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto("/marketplace/?q=capacity-that-does-not-exist&sort=price");

    await expect(page.locator(".marketplace-empty-state")).toContainText("No matching manufacturing capacity found.");
    await expect(page.locator(".marketplace-empty-state")).toContainText("capacity-that-does-not-exist");
    await expect(page.getByRole("link", { name: "Clear filters" })).toHaveAttribute("href", "/marketplace/?sort=price");
    await expect(page.getByRole("link", { name: "Browse all listings" })).toHaveAttribute("href", "/marketplace/");

    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/marketplace/?location=dAdRa%20aNd%20NaGaR%20hAvElI%20aNd%20DaMaN%20aNd%20DiU");
      await expect(page.locator(".marketplace-filter-chips")).toContainText(
        "Location: Dadra and Nagar Haveli and Daman and Diu"
      );

      const filterPanel = page.locator(".marketplace-filter-disclosure");
      await expect(filterPanel).toHaveJSProperty("open", false);
      await filterPanel.locator("summary").click();
      await expect(filterPanel.getByLabel("Location")).toHaveValue("dAdRa aNd NaGaR hAvElI aNd DaMaN aNd DiU");
      await filterPanel.getByRole("button", { name: "Close filters" }).click();
      await expect(filterPanel).toHaveJSProperty("open", false);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    }
  });
});
