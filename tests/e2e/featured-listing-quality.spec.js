const { execFileSync } = require("node:child_process");
const { test, expect } = require("@playwright/test");
const { dismissCookieBanner } = require("./helpers");

function runLocalDjango(code) {
  const python = process.platform === "win32" ? "venv/Scripts/python.exe" : "python";
  return execFileSync(
    python,
    ["manage.py", "shell", "--settings=config.settings_e2e", "-c", code],
    { cwd: process.cwd(), encoding: "utf8" }
  ).trim();
}

test("homepage promotes only an explicitly featured eligible listing", async ({ page }) => {
  test.skip(Boolean(process.env.UBHAAR_BASE_URL), "Listing fixtures are limited to the local E2E database.");

  const fixtureOutput = runLocalDjango(`
import json, uuid
from decimal import Decimal
from django.contrib.auth import get_user_model
from marketplace.models import CapacityListing, ManufacturerProfile

User = get_user_model()
suffix = uuid.uuid4().hex[:12]
prefix = f"uv-featured-e2e-{suffix}"
user = User.objects.create_user(
    username=f"{prefix}-maker",
    email=f"{prefix}@example.com",
    role="MANUFACTURER",
)
profile = ManufacturerProfile.objects.create(
    user=user,
    business_name=f"Verified featured maker {suffix}",
    city="Pune",
    state="maharashtra",
    is_verified=True,
)
eligible = CapacityListing.objects.create(
    manufacturer=profile,
    title=f"Curated featured capacity {suffix}",
    description="Verified local E2E capacity fixture.",
    category=CapacityListing.Category.METAL,
    minimum_quantity=1,
    price_per_unit=Decimal("12.00"),
    production_days=1,
    availability_status=CapacityListing.AvailabilityStatus.AVAILABLE,
    is_active=True,
    is_featured=True,
    image="e2e-featured.svg",
)
unfeatured = CapacityListing.objects.create(
    manufacturer=profile,
    title=f"Unfeatured recent capacity {suffix}",
    description="Must not be promoted automatically.",
    category=CapacityListing.Category.METAL,
    minimum_quantity=1,
    price_per_unit=Decimal("12.00"),
    production_days=1,
    availability_status=CapacityListing.AvailabilityStatus.AVAILABLE,
    is_active=True,
    is_featured=False,
    image="e2e-featured.svg",
)
print(json.dumps({"suffix": suffix, "maker": user.username, "eligible": eligible.title, "unfeatured": unfeatured.title}))
`);
  const fixture = JSON.parse(fixtureOutput.split(/\r?\n/).filter(Boolean).at(-1));

  try {
    await page.route("**/e2e-featured.svg", (route) =>
      route.fulfill({
        status: 200,
        contentType: "image/svg+xml",
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="9"><rect width="16" height="9" fill="#526b61"/></svg>'
      })
    );

    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 850 });
      await page.goto("/");
      await dismissCookieBanner(page);

      const section = page.locator(".landing-featured");
      await expect(section).toBeVisible();
      await expect(section.getByRole("link", { name: fixture.eligible, exact: true })).toBeVisible();
      await expect(section).not.toContainText(fixture.unfeatured);
      await expect(section.getByRole("link", { name: "Browse marketplace" })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    }
  } finally {
    const usernamePrefix = `uv-featured-e2e-${fixture.suffix}-`;
    runLocalDjango(`
from django.contrib.auth import get_user_model
User = get_user_model()
User.objects.filter(username__startswith=${JSON.stringify(usernamePrefix)}).delete()
`);
  }
});
