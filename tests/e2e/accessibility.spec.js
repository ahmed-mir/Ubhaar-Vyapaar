const { test, expect } = require("@playwright/test");

test.describe("accessibility and keyboard UX", () => {
  test("mobile navigation opens, closes, and returns focus with keyboard", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto("/");

    const toggle = page.locator(".nav-toggle");
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAccessibleName(/open main navigation/i);
    await toggle.focus();
    await page.keyboard.press("Enter");

    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(toggle).toHaveAccessibleName(/close main navigation/i);
    await expect(page.getByRole("navigation", { name: /main navigation/i })).toBeVisible();

    await page.keyboard.press("Escape");

    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(toggle).toHaveAccessibleName(/open main navigation/i);
    await expect(toggle).toBeFocused();
  });

  test("registration errors are associated with invalid fields", async ({ page }) => {
    await page.goto("/accounts/register/");
    await page.getByRole("button", { name: /create buyer account/i }).click();

    const username = page.locator("[name='username']");
    await expect(username).toHaveAttribute("aria-invalid", "true");
    await expect(username).toHaveAttribute("aria-describedby", /id_username_error/);
    await expect(page.locator("#id_username_error")).toHaveCount(1);
    await expect(page.locator("#id_username_error")).toBeVisible();
  });

  test("skip link moves keyboard users to main content", async ({ page }) => {
    await page.goto("/");

    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: /skip to content/i })).toBeFocused();
    await page.keyboard.press("Enter");

    await expect(page.locator("#main-content")).toBeFocused();
  });

  test("FAQ groups and disclosures work with keyboard on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    await page.goto("/faq/");

    await expect(page.getByRole("heading", { level: 2, name: "Getting started" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: "Verification and payments" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: /on this page/i })).toHaveCount(0);

    const paymentSummary = page.getByText("Does Ubhaar-Vyapaar process payments?", { exact: true });
    await paymentSummary.focus();
    await page.keyboard.press("Enter");
    await expect(paymentSummary.locator("xpath=.." )).toHaveAttribute("open", "");
    await expect(page.getByText(/does not process real payments/i)).toBeVisible();
    await page.keyboard.press("Space");
    await expect(paymentSummary.locator("xpath=.." )).not.toHaveAttribute("open", "");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
  });

  test("marketplace filters, pagination, listing, and manufacturer navigation work by keyboard", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto("/marketplace/");

    const filters = page.locator(".marketplace-filter-disclosure");
    const summary = filters.locator("summary");
    await summary.focus();
    await page.keyboard.press("Enter");
    await expect(filters).toHaveAttribute("open", "");

    const location = page.getByLabel("Location");
    await location.focus();
    await page.keyboard.type("Pune");
    await filters.getByRole("button", { name: /apply filters/i }).focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/location=Pune/);

    const removeLocation = page.getByRole("link", { name: /remove location: pune filter/i });
    await removeLocation.focus();
    await page.keyboard.press("Enter");
    await expect(page).not.toHaveURL(/location=/);

    await page.goto("/marketplace/");
    const next = page.getByRole("link", { name: /next/i });
    await next.focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/page=2/);

    const listing = page.locator(".listing-spec-main h3 a").first();
    await listing.focus();
    await page.keyboard.press("Enter");
    await expect(page.locator("h1")).toBeVisible();

    const manufacturer = page.locator('a[href*="/manufacturers/"]').first();
    await manufacturer.focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/manufacturers\/\d+\//);
  });

  test("reduced motion preference disables reveal dependency", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/marketplace/");

    const hero = page.locator(".marketplace-heading");
    await expect(hero).toBeVisible();
    await expect(hero).toHaveCSS("transform", "none");
  });
});
